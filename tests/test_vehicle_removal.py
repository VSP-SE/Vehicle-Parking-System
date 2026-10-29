"""FR-VEH-04 – Protect vehicles that have live bookings (#29)."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from vps.accounts.models import User
from vps.lots.models import Lot, Slot
from vps.reservations.models import Reservation
from vps.vehicles.models import Vehicle
from vps.vehicles.services import remove_vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def driver():
    return User.objects.create_user(email="driver@example.com", password="password")


@pytest.fixture
def vehicle(driver):
    return Vehicle.objects.create(
        owner=driver,
        registration_no="KA01AB1234",
        vehicle_type=Vehicle.VehicleType.CAR,
    )


@pytest.fixture
def slot():
    lot = Lot.objects.create(
        name="Lot A", address="1 Ring Road",
        opens_at="06:00", closes_at="23:00"
    )
    return Slot.objects.create(lot=lot, code="A-01", distance_rank=1)


def make_reservation(vehicle, slot, status=Reservation.Status.RESERVED):
    start = timezone.now() + timedelta(hours=1)
    end = start + timedelta(hours=2)
    return Reservation.objects.create(
        booking_ref=f"VPS-{timezone.now():%y%m%d}-{vehicle.pk:04d}",
        vehicle_reg_no=vehicle.registration_no,
        slot=slot,
        period=(start, end),
        status=status,
        driver=vehicle.owner,
    )


def test_remove_vehicle_without_booking_succeeds(vehicle):
    result = remove_vehicle(vehicle)
    assert result.is_active is False
    vehicle.refresh_from_db()
    assert vehicle.is_active is False


def test_remove_already_inactive_vehicle_is_idempotent(vehicle):
    vehicle.is_active = False
    vehicle.save()
    result = remove_vehicle(vehicle)
    assert result.is_active is False


def test_cannot_remove_vehicle_with_reserved_booking(vehicle, slot):
    make_reservation(vehicle, slot, status=Reservation.Status.RESERVED)
    with pytest.raises(ValidationError) as exc:
        remove_vehicle(vehicle)
    assert "active or reserved booking" in str(exc.value)
    vehicle.refresh_from_db()
    assert vehicle.is_active is True


def test_cannot_remove_vehicle_with_active_booking(vehicle, slot):
    make_reservation(vehicle, slot, status=Reservation.Status.ACTIVE)
    with pytest.raises(ValidationError) as exc:
        remove_vehicle(vehicle)
    assert "active or reserved booking" in str(exc.value)
    vehicle.refresh_from_db()
    assert vehicle.is_active is True


@pytest.mark.parametrize(
    "status",
    [
        Reservation.Status.COMPLETED,
        Reservation.Status.CANCELLED,
        Reservation.Status.EXPIRED,
    ],
)
def test_can_remove_vehicle_with_finished_booking(vehicle, slot, status):
    make_reservation(vehicle, slot, status=status)
    result = remove_vehicle(vehicle)
    assert result.is_active is False