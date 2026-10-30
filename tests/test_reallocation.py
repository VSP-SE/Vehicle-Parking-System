"""FR-GATE-07 / TC-32: check-in moves a booking off a slot an overstaying vehicle still holds."""

from datetime import datetime, time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.urls import reverse
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.gate import services
from vps.lots.models import Lot, Slot
from vps.reservations.models import Reservation
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db
NOON = timezone.make_aware(datetime(2026, 10, 28, 12))


@pytest.fixture
def attendant():
    return User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)


@pytest.fixture
def lot():
    return Lot.objects.create(
        name="Lot A", address="Ring Road", opens_at=time(6), closes_at=time(23)
    )


def slot(lot, code, rank, slot_type="Standard"):
    return Slot.objects.create(lot=lot, code=code, distance_rank=rank, slot_type=slot_type)


def overstayer(on, ref="VPS-261028-0009", reg="KA09ZZ0009"):
    """A vehicle booked 09:00-11:30 that has not checked out."""
    start = NOON - timedelta(hours=3)
    return Reservation.objects.create(
        booking_ref=ref,
        vehicle_reg_no=reg,
        slot=on,
        period=DateTimeTZRange(start, NOON - timedelta(minutes=30)),
        status=Reservation.Status.ACTIVE,
        entry_time=start,
    )


def booking(on, vehicle_type="Car"):
    driver = User.objects.create_user(email="r@example.com")
    Vehicle.objects.create(owner=driver, registration_no="KA01AB1234", vehicle_type=vehicle_type)
    return Reservation.objects.create(
        booking_ref="VPS-261028-0001",
        driver=driver,
        vehicle_reg_no="KA01AB1234",
        slot=on,
        period=DateTimeTZRange(NOON, NOON + timedelta(hours=2)),
    )


def test_tc32_occupied_slot_is_swapped_for_a_free_one(lot, attendant):
    s1, s2 = slot(lot, "S1", 1), slot(lot, "S2", 2)
    overstayer(s1)
    r = booking(s1)

    result = services.check_in_vehicle(r.booking_ref, attendant, now=NOON)

    r.refresh_from_db()
    assert r.status == Reservation.Status.ACTIVE
    assert r.slot == s2
    assert result.slot.code == "S2"
    assert result.reallocated_from == "S1"
    log = AuditLog.objects.get(action="reservation.checked_in")
    assert log.after["slot"] == "S2"
    assert log.after["reallocated_from"] == "S1"


def test_free_slot_is_kept(lot, attendant):
    s1 = slot(lot, "S1", 1)
    slot(lot, "S2", 2)
    r = booking(s1)

    result = services.check_in_vehicle(r.booking_ref, attendant, now=NOON)

    assert result.slot == s1
    assert result.reallocated_from is None
    assert "reallocated_from" not in AuditLog.objects.get().after


def test_skips_slots_held_by_other_overstayers_and_ineligible_ones(lot, attendant):
    s1, s2 = slot(lot, "S1", 1), slot(lot, "S2", 2)
    slot(lot, "T1", 1, "TwoWheeler")
    slot(lot, "H1", 1, "Accessible")
    s3 = slot(lot, "S3", 3)
    overstayer(s1)
    overstayer(s2, "VPS-261028-0010", "KA09ZZ0010")
    r = booking(s1)

    assert services.check_in_vehicle(r.booking_ref, attendant, now=NOON).slot == s3


def test_ev_prefers_a_free_ev_slot(lot, attendant):
    e1 = slot(lot, "E1", 1, "EV")
    slot(lot, "S1", 1)
    e2 = slot(lot, "E2", 5, "EV")
    overstayer(e1)
    r = booking(e1, "EV")

    assert services.check_in_vehicle(r.booking_ref, attendant, now=NOON).slot == e2


def test_no_free_slot_refuses_and_changes_nothing(lot, attendant):
    s1, s2 = slot(lot, "S1", 1), slot(lot, "S2", 2)
    overstayer(s1)
    Reservation.objects.create(
        booking_ref="VPS-261028-0002",
        vehicle_reg_no="KA02CD0002",
        slot=s2,
        period=DateTimeTZRange(NOON - timedelta(minutes=30), NOON + timedelta(hours=1)),
    )
    r = booking(s1)

    with pytest.raises(ValidationError) as error:
        services.check_in_vehicle(r.booking_ref, attendant, now=NOON)

    assert error.value.messages == [services.SLOT_STILL_OCCUPIED]
    r.refresh_from_db()
    assert (r.status, r.slot, r.entry_time) == (Reservation.Status.RESERVED, s1, None)
    assert not AuditLog.objects.exists()


def test_console_shows_the_new_slot(client, lot, attendant):
    s1 = slot(lot, "S1", 1)
    slot(lot, "S2", 2)
    overstayer(s1)
    start = timezone.now()
    r = booking(s1)
    Reservation.objects.filter(pk=r.pk).update(
        period=DateTimeTZRange(start, start + timedelta(hours=2))
    )
    Reservation.objects.filter(slot=s1, status="Active").update(
        period=DateTimeTZRange(start - timedelta(hours=3), start - timedelta(minutes=30))
    )
    client.force_login(attendant)

    response = client.post(reverse("gate:checkin"), {"reference": r.booking_ref})

    assert "Slot S1 is still occupied. Park in slot S2." in response.content.decode()


def test_removed_vehicle_record_does_not_decide_the_slot_type(lot, attendant):
    """The plate was a Car, removed, then re-registered as a two-wheeler."""
    t1, t2 = slot(lot, "T1", 1, "TwoWheeler"), slot(lot, "T2", 2, "TwoWheeler")
    slot(lot, "S1", 1)
    overstayer(t1)
    r = booking(t1, "TwoWheeler")
    # The removed Car record is newer than the active two-wheeler one.
    Vehicle.objects.create(
        owner=r.driver, registration_no="KA01AB1234", vehicle_type="Car", is_active=False
    )

    assert services.check_in_vehicle(r.booking_ref, attendant, now=NOON).slot == t2
