"""FR-ALLOC-01 – Slot eligibility rules (#36)."""

from datetime import time

import pytest

from vps.accounts.models import User
from vps.allocation.services import eligible_slot_types, is_slot_eligible
from vps.lots.models import Lot, Slot
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def lot():
    return Lot.objects.create(
        name="Test Lot", address="Test Road", opens_at=time(6), closes_at=time(23)
    )


@pytest.fixture
def make_slot(lot):
    def _make(code, slot_type, rank=1):
        return Slot.objects.create(
            lot=lot, code=code, slot_type=slot_type, distance_rank=rank
        )
    return _make


@pytest.fixture
def make_vehicle():
    counter = {"n": 0}

    def _make(vehicle_type, *, accessible_permit=False):
        counter["n"] += 1
        owner = User.objects.create_user(
            email=f"{vehicle_type.lower()}{counter['n']}@example.com",
            password="password",
            accessible_permit=accessible_permit,
        )
        return Vehicle.objects.create(
            owner=owner,
            registration_no=f"KA01{vehicle_type[:2].upper()}{counter['n']:04d}",
            vehicle_type=vehicle_type,
        )

    return _make


# ---------- Two-wheeler ----------

def test_two_wheeler_only_two_wheeler_slots(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.TWO_WHEELER)
    tw = make_slot("T1", Slot.SlotType.TWO_WHEELER)
    std = make_slot("S1", Slot.SlotType.STANDARD)
    ev = make_slot("E1", Slot.SlotType.EV)
    acc = make_slot("A1", Slot.SlotType.ACCESSIBLE)

    assert is_slot_eligible(tw, vehicle) is True
    assert is_slot_eligible(std, vehicle) is False
    assert is_slot_eligible(ev, vehicle) is False
    assert is_slot_eligible(acc, vehicle) is False
    assert eligible_slot_types(vehicle) == {Slot.SlotType.TWO_WHEELER}


# ---------- Car ----------

def test_car_standard_always_allowed(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.CAR)
    std = make_slot("S1", Slot.SlotType.STANDARD)
    assert is_slot_eligible(std, vehicle) is True


def test_car_accessible_only_with_permit(make_slot, make_vehicle):
    no_permit = make_vehicle(Vehicle.VehicleType.CAR, accessible_permit=False)
    with_permit = make_vehicle(Vehicle.VehicleType.CAR, accessible_permit=True)
    acc = make_slot("A1", Slot.SlotType.ACCESSIBLE)

    assert is_slot_eligible(acc, no_permit) is False
    assert is_slot_eligible(acc, with_permit) is True


def test_car_never_gets_two_wheeler_or_ev(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.CAR, accessible_permit=True)
    tw = make_slot("T1", Slot.SlotType.TWO_WHEELER)
    ev = make_slot("E1", Slot.SlotType.EV)

    assert is_slot_eligible(tw, vehicle) is False
    assert is_slot_eligible(ev, vehicle) is False


def test_car_eligible_types_with_and_without_permit(make_vehicle):
    no_permit = make_vehicle(Vehicle.VehicleType.CAR, accessible_permit=False)
    with_permit = make_vehicle(Vehicle.VehicleType.CAR, accessible_permit=True)

    assert eligible_slot_types(no_permit) == {Slot.SlotType.STANDARD}
    assert eligible_slot_types(with_permit) == {
        Slot.SlotType.STANDARD,
        Slot.SlotType.ACCESSIBLE,
    }


# ---------- Electric vehicle ----------

def test_ev_can_use_ev_and_standard(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.EV)
    ev = make_slot("E1", Slot.SlotType.EV)
    std = make_slot("S1", Slot.SlotType.STANDARD)
    tw = make_slot("T1", Slot.SlotType.TWO_WHEELER)
    acc = make_slot("A1", Slot.SlotType.ACCESSIBLE)

    assert is_slot_eligible(ev, vehicle) is True
    assert is_slot_eligible(std, vehicle) is True
    assert is_slot_eligible(tw, vehicle) is False
    assert is_slot_eligible(acc, vehicle) is False
    assert eligible_slot_types(vehicle) == {
        Slot.SlotType.EV,
        Slot.SlotType.STANDARD,
    }