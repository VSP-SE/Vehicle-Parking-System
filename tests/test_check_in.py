"""FR-GATE-01 / FR-GATE-02 – Check in a booked vehicle (#46)."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from vps.accounts.models import User
from vps.gate.services import check_in_vehicle
from vps.lots.models import Lot, Slot
from vps.reservations.models import Reservation

pytestmark = pytest.mark.django_db


@pytest.fixture
def attendant():
    return User.objects.create_user(
        email="attendant@example.com",
        password="password",
        role=User.Role.ATTENDANT,
    )


@pytest.fixture
def driver():
    return User.objects.create_user(
        email="driver@example.com",
        password="password",
        role=User.Role.DRIVER,
    )


@pytest.fixture
def slot():
    lot = Lot.objects.create(
        name="Lot A", address="1 Ring Road", opens_at="06:00", closes_at="23:00"
    )
    return Slot.objects.create(lot=lot, code="A-01", distance_rank=1)


def make_reservation(driver, slot, start, status=Reservation.Status.RESERVED):
    end = start + timedelta(hours=2)
    return Reservation.objects.create(
        booking_ref=f"VPS-TEST-{timezone.now():%H%M%S}",
        driver=driver,
        vehicle_reg_no="KA01AB1234",
        slot=slot,
        period=(start, end),
        status=status,
    )


def test_check_in_success_within_window(attendant, driver, slot):
    start = timezone.now() + timedelta(minutes=5)
    reservation = make_reservation(driver, slot, start)

    result = check_in_vehicle(reservation.booking_ref, attendant)

    assert result.status == Reservation.Status.ACTIVE
    assert result.entry_time is not None
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.ACTIVE


def test_check_in_by_registration_number(attendant, driver, slot):
    start = timezone.now() + timedelta(minutes=5)
    reservation = make_reservation(driver, slot, start)

    result = check_in_vehicle("KA01AB1234", attendant)
    assert result.pk == reservation.pk
    assert result.status == Reservation.Status.ACTIVE


def test_check_in_too_early(attendant, driver, slot):
    start = timezone.now() + timedelta(minutes=30)
    reservation = make_reservation(driver, slot, start)

    with pytest.raises(ValidationError) as exc:
        check_in_vehicle(reservation.booking_ref, attendant)

    assert "Too early" in str(exc.value)
    assert "Earliest allowed time" in str(exc.value)
    reservation.refresh_from_db()
    assert reservation.status == Reservation.Status.RESERVED


def test_check_in_window_closed(attendant, driver, slot):
    start = timezone.now() - timedelta(minutes=20)
    reservation = make_reservation(driver, slot, start)

    with pytest.raises(ValidationError) as exc:
        check_in_vehicle(reservation.booking_ref, attendant)

    assert "check-in window has closed" in str(exc.value).lower()


def test_check_in_rejects_non_reserved(attendant, driver, slot):
    start = timezone.now() + timedelta(minutes=5)
    reservation = make_reservation(driver, slot, start, status=Reservation.Status.ACTIVE)

    with pytest.raises(ValidationError) as exc:
        check_in_vehicle(reservation.booking_ref, attendant)

    assert "No Reserved reservation" in str(exc.value)


def test_check_in_requires_attendant_role(driver, slot):
    start = timezone.now() + timedelta(minutes=5)
    reservation = make_reservation(driver, slot, start)

    with pytest.raises(ValidationError) as exc:
        check_in_vehicle(reservation.booking_ref, driver)  # driver is not attendant

    assert "Only Gate Attendants" in str(exc.value)


def test_registration_picks_the_booking_in_its_window(attendant, driver, slot):
    """Tomorrow's booking, made after today's, must not hide today's from a plate lookup."""
    now = timezone.now()
    for ref, start in (("VPS-TEST-TDAY", now), ("VPS-TEST-TMRW", now + timedelta(days=1))):
        Reservation.objects.create(
            booking_ref=ref,
            driver=driver,
            vehicle_reg_no="KA01AB1234",
            slot=slot,
            period=(start, start + timedelta(hours=2)),
        )

    result = check_in_vehicle("ka01ab1234", attendant, now=now)

    assert result.booking_ref == "VPS-TEST-TDAY"
    assert Reservation.objects.get(booking_ref="VPS-TEST-TMRW").status == "Reserved"


def test_too_early_message_names_the_day(attendant, driver, slot):
    start = timezone.now() + timedelta(days=1)
    reservation = make_reservation(driver, slot, start)
    with pytest.raises(ValidationError) as error:
        check_in_vehicle(reservation.booking_ref, attendant)
    earliest = timezone.localtime(start - timedelta(minutes=15))
    assert f"{earliest:%d %b %H:%M}" in error.value.messages[0]


def test_check_in_reallocates_when_slot_occupied(attendant, driver, slot):
    """FR-GATE-07: if the booked slot is occupied, give another free slot."""
    now = timezone.now()
    start = now + timedelta(minutes=5)
    end = start + timedelta(hours=2)

    reservation = Reservation.objects.create(
        booking_ref="VPS-RA-001",
        driver=driver,
        vehicle_reg_no="KA01AB1234",
        slot=slot,
        period=(start, end),
        status=Reservation.Status.RESERVED,
    )

    free_slot = Slot.objects.create(
        lot=slot.lot,
        code="A-02",
        slot_type=slot.slot_type,
        distance_rank=2,
    )

    # Overstaying Active reservation (period ends before the new one starts)
    Reservation.objects.create(
        booking_ref="VPS-OS-001",
        vehicle_reg_no="KA99ZZ9999",
        slot=slot,
        period=(now - timedelta(hours=5), now - timedelta(minutes=10)),
        status=Reservation.Status.ACTIVE,
        entry_time=now - timedelta(hours=5),
    )

    result = check_in_vehicle(reservation.booking_ref, attendant)

    assert result.status == Reservation.Status.ACTIVE
    assert result.slot.pk == free_slot.pk
    assert result.slot.code == "A-02"
