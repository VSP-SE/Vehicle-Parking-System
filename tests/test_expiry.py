"""FR-RES-05 / TC-10: expire no-shows, release slots and enforce BR-04."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.billing.models import Charge
from vps.lots.models import Lot, Slot
from vps.reservations import services
from vps.reservations.models import Reservation
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db
START = timezone.localtime().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(
    days=1
)


@pytest.fixture
def booking():
    driver = User.objects.create_user(email="driver@example.com")
    car = Vehicle.objects.create(
        owner=driver, registration_no="KA01AB1234", vehicle_type="Car"
    )
    lot = Lot.objects.create(
        name="Lot A", address="Ring Road", opens_at=time(6), closes_at=time(23)
    )
    slot = Slot.objects.create(lot=lot, code="S1", distance_rank=1)
    return Reservation.objects.create(
        booking_ref="VPS-261028-0001",
        driver=driver,
        vehicle_reg_no=car.registration_no,
        slot=slot,
        period=DateTimeTZRange(START, START + timedelta(hours=2)),
    )


def test_tc10_expires_only_after_grace_period_and_releases_slot(booking):
    assert services.expire_no_shows(now=START + timedelta(minutes=14)) == 0
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.RESERVED
    assert not Charge.objects.exists()
    assert not AuditLog.objects.exists()

    assert services.expire_no_shows(now=START + timedelta(minutes=16)) == 1
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.EXPIRED
    charge = Charge.objects.get()
    assert charge.reservation == booking
    assert charge.kind == Charge.Kind.NO_SHOW
    assert charge.amount_inr == Decimal("50.00")
    audit = AuditLog.objects.get()
    assert audit.actor is None
    assert audit.action == "reservation.expired"
    assert audit.target == f"reservation:{booking.booking_ref}"
    assert audit.before == {"status": "Reserved"}
    assert audit.after == {"status": "Expired"}

    # The real PostgreSQL exclusion constraint must permit an overlapping replacement.
    replacement = Reservation.objects.create(
        booking_ref="VPS-261028-0002",
        vehicle_reg_no="KA02CD5678",
        slot=booking.slot,
        period=booking.period,
    )
    assert replacement.status == Reservation.Status.RESERVED


def test_exactly_fifteen_minutes_is_still_reserved(booking):
    assert services.expire_no_shows(now=START + timedelta(minutes=15)) == 0
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.RESERVED
    assert not Charge.objects.exists()
    assert not AuditLog.objects.exists()


def test_expiry_is_idempotent(booking):
    now = START + timedelta(minutes=16)
    assert services.expire_no_shows(now=now) == 1
    assert services.expire_no_shows(now=now) == 0
    assert Charge.objects.count() == AuditLog.objects.count() == 1


@pytest.mark.parametrize("status", ["Active", "Cancelled", "Completed", "Expired"])
def test_other_statuses_are_untouched(booking, status):
    booking.status = status
    booking.save(update_fields=["status"])
    assert services.expire_no_shows(now=START + timedelta(minutes=16)) == 0
    booking.refresh_from_db()
    assert booking.status == status
    assert not Charge.objects.exists()
    assert not AuditLog.objects.exists()


def test_command_uses_current_time_and_prints_count(booking, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: START + timedelta(minutes=16))
    output = StringIO()
    call_command("expire_no_shows", stdout=output)
    assert output.getvalue() == "Expired 1 no-show reservations.\n"
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.EXPIRED
    output = StringIO()
    call_command("expire_no_shows", stdout=output)
    assert output.getvalue() == "Expired 0 no-show reservations.\n"


def test_unpaid_no_show_charge_blocks_reserve_br04(booking):
    services.expire_no_shows(now=START + timedelta(minutes=16))
    with pytest.raises(ValidationError) as error:
        services.reserve(
            booking.driver,
            booking.driver.vehicles.get(),
            booking.slot.lot,
            START,
            START + timedelta(hours=1),
        )
    assert error.value.message_dict == {"__all__": [services.UNPAID_CHARGE]}


def test_audit_failure_rolls_back_expiry_and_charge(booking, monkeypatch):
    def fail_audit(**kwargs):
        raise IntegrityError("Audit insert failed")

    monkeypatch.setattr(AuditLog.objects, "create", fail_audit)
    with pytest.raises(IntegrityError, match="Audit insert failed"):
        services.expire_no_shows(now=START + timedelta(minutes=16))
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.RESERVED
    assert not Charge.objects.exists()
    assert not AuditLog.objects.exists()


def _expire_in_thread(barrier):
    try:
        barrier.wait(timeout=10)
        return services.expire_no_shows(now=START + timedelta(minutes=16))
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
def test_concurrent_jobs_expire_and_charge_once(booking):
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _expire_in_thread(barrier), range(2)))
    assert sorted(results) == [0, 1]
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.EXPIRED
    assert Charge.objects.count() == AuditLog.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_job_skips_locked_reservation(booking):
    with transaction.atomic():
        Reservation.objects.select_for_update().get(pk=booking.pk)
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(_expire_in_thread, threading.Barrier(1)).result(timeout=10)
        assert result == 0
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.RESERVED
    assert not Charge.objects.exists()
    assert not AuditLog.objects.exists()
    assert services.expire_no_shows(now=START + timedelta(minutes=16)) == 1
