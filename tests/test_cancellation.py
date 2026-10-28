"""Cancelling a reservation (FR-RES-04, TC-09)."""

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.billing.models import Charge
from vps.lots.models import Lot, Slot
from vps.reservations import services
from vps.reservations.models import Reservation

pytestmark = pytest.mark.django_db
NOW = timezone.make_aware(timezone.datetime(2026, 10, 28, 9, 0))


@pytest.fixture
def driver():
    return User.objects.create_user(email="driver@example.com")


@pytest.fixture
def slot():
    lot = Lot.objects.create(
        name="Lot A", address="1 Ring Road", opens_at=time(6), closes_at=time(23)
    )
    return Slot.objects.create(lot=lot, code="A-01", distance_rank=1)


def booking(driver, slot, starts_in, status=Reservation.Status.RESERVED, ref="VPS-261028-0001"):
    start = NOW + starts_in
    return Reservation.objects.create(
        booking_ref=ref,
        driver=driver,
        vehicle_reg_no="KA01AB1234",
        slot=slot,
        period=DateTimeTZRange(start, start + timedelta(hours=2)),
        status=status,
    )


def cancel(driver, reservation, now=NOW):
    return services.cancel_reservation(driver=driver, reservation_id=reservation.pk, now=now)


def test_tc09_early_cancellation_is_free(driver, slot):
    """TC-09 R1: 90 minutes ahead is Cancelled with no charge."""
    r1 = booking(driver, slot, timedelta(minutes=90))
    assert cancel(driver, r1).status == Reservation.Status.CANCELLED
    assert not Charge.objects.exists()


def test_tc09_late_cancellation_charges_rs30(driver, slot):
    """TC-09 R2: 30 minutes ahead is Cancelled with a Rs 30.00 late-cancellation charge."""
    r2 = booking(driver, slot, timedelta(minutes=30))
    cancel(driver, r2)
    charge = Charge.objects.get()
    assert (charge.reservation, charge.kind, charge.amount_inr) == (
        r2,
        Charge.Kind.LATE_CANCEL,
        Decimal("30.00"),
    )


def test_exactly_sixty_minutes_ahead_is_free(driver, slot):
    cancel(driver, booking(driver, slot, timedelta(minutes=60)))
    assert not Charge.objects.exists()


@pytest.mark.parametrize("starts_in", [timedelta(0), timedelta(minutes=-5)])
def test_cannot_cancel_at_or_after_start(driver, slot, starts_in):
    reservation = booking(driver, slot, starts_in)
    with pytest.raises(ValidationError):
        cancel(driver, reservation)
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.RESERVED


@pytest.mark.parametrize(
    "status", [Reservation.Status.ACTIVE, Reservation.Status.CANCELLED, Reservation.Status.EXPIRED]
)
def test_only_reserved_bookings_can_be_cancelled(driver, slot, status):
    with pytest.raises(ValidationError):
        cancel(driver, booking(driver, slot, timedelta(hours=3), status=status))
    assert not Charge.objects.exists()


def test_cancelling_frees_the_slot_and_is_audited(driver, slot):
    reservation = booking(driver, slot, timedelta(hours=3))
    cancel(driver, reservation)
    booking(driver, slot, timedelta(hours=3), ref="VPS-261028-0002")
    entry = AuditLog.objects.get(action="reservation.cancelled")
    assert entry.actor == driver
    assert entry.before == {"status": "Reserved"}
    assert entry.after["status"] == "Cancelled"


def test_drivers_cannot_cancel_someone_elses_booking(driver, slot):
    other = User.objects.create_user(email="other@example.com")
    with pytest.raises(Reservation.DoesNotExist):
        cancel(other, booking(driver, slot, timedelta(hours=3)))


def test_cancel_view_reports_late_fee_and_free_cancellation(client, driver, slot):
    late = booking(driver, slot, timedelta(minutes=30))
    early = booking(driver, slot, timedelta(hours=5), ref="VPS-261028-0002")
    late.period = DateTimeTZRange(
        timezone.now() + timedelta(minutes=30), timezone.now() + timedelta(hours=2)
    )
    late.save()
    early.period = DateTimeTZRange(
        timezone.now() + timedelta(hours=5), timezone.now() + timedelta(hours=6)
    )
    early.save()
    client.force_login(driver)

    late_page = client.post(f"/reservations/{late.pk}/cancel/", follow=True).content.decode()
    early_page = client.post(f"/reservations/{early.pk}/cancel/", follow=True).content.decode()

    assert "late-cancellation charge of Rs 30" in late_page
    assert "cancelled free of charge" in early_page


def test_cancel_view_errors_404_and_roles(client, driver, slot):
    reservation = booking(driver, slot, timedelta(minutes=-5))
    reservation.period = DateTimeTZRange(
        timezone.now() - timedelta(minutes=5), timezone.now() + timedelta(hours=1)
    )
    reservation.save()
    client.force_login(driver)
    assert (
        "before their start time"
        in client.post(f"/reservations/{reservation.pk}/cancel/", follow=True).content.decode()
    )
    assert client.post("/reservations/999999/cancel/").status_code == 404
    assert client.get(f"/reservations/{reservation.pk}/cancel/").status_code == 405

    client.force_login(User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT))
    assert client.post(f"/reservations/{reservation.pk}/cancel/").status_code == 403
