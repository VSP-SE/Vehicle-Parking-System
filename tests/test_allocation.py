"""FR-ALLOC-01 + FR-ALLOC-02 – Slot eligibility and deterministic choice."""

from datetime import time

import pytest

from vps.accounts.models import User
from vps.allocation.services import (
    choose_best_slot,
    eligible_slot_types,
    is_slot_eligible,
)
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


# ---------- Eligibility tests (from #36) ----------

def test_two_wheeler_only_two_wheeler_slots(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.TWO_WHEELER)
    tw = make_slot("T1", Slot.SlotType.TWO_WHEELER)
    std = make_slot("S1", Slot.SlotType.STANDARD)
    assert is_slot_eligible(tw, vehicle) is True
    assert is_slot_eligible(std, vehicle) is False


def test_car_accessible_only_with_permit(make_slot, make_vehicle):
    no_permit = make_vehicle(Vehicle.VehicleType.CAR, accessible_permit=False)
    with_permit = make_vehicle(Vehicle.VehicleType.CAR, accessible_permit=True)
    acc = make_slot("A1", Slot.SlotType.ACCESSIBLE)
    assert is_slot_eligible(acc, no_permit) is False
    assert is_slot_eligible(acc, with_permit) is True


def test_ev_can_use_ev_and_standard(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.EV)
    ev = make_slot("E1", Slot.SlotType.EV)
    std = make_slot("S1", Slot.SlotType.STANDARD)
    assert is_slot_eligible(ev, vehicle) is True
    assert is_slot_eligible(std, vehicle) is True


# ---------- Deterministic choice tests (#37) ----------

def test_choose_best_slot_prefers_type_then_rank_then_code(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.EV)

    # Create slots out of order on purpose
    s_far = make_slot("S9", Slot.SlotType.STANDARD, rank=5)
    e_far = make_slot("E9", Slot.SlotType.EV, rank=5)
    e_near = make_slot("E1", Slot.SlotType.EV, rank=1)
    s_near = make_slot("S1", Slot.SlotType.STANDARD, rank=1)
    e_near_b = make_slot("E2", Slot.SlotType.EV, rank=1)  # same rank, higher code

    candidates = [s_far, e_far, e_near_b, s_near, e_near]
    best = choose_best_slot(candidates, vehicle)

    # Should pick the nearest EV with the lowest code
    assert best == e_near


def test_choose_best_slot_falls_back_to_standard_for_ev(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.EV)
    s1 = make_slot("S1", Slot.SlotType.STANDARD, rank=1)
    s2 = make_slot("S2", Slot.SlotType.STANDARD, rank=2)

    best = choose_best_slot([s2, s1], vehicle)
    assert best == s1  # lowest rank


def test_choose_best_slot_for_car_prefers_standard(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.CAR, accessible_permit=True)
    acc = make_slot("A1", Slot.SlotType.ACCESSIBLE, rank=1)
    std = make_slot("S5", Slot.SlotType.STANDARD, rank=3)

    best = choose_best_slot([acc, std], vehicle)
    assert best == std  # Standard preferred over Accessible


def test_choose_best_slot_empty_list_returns_none(make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.CAR)
    assert choose_best_slot([], vehicle) is None


def test_car_standard_always_allowed(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.CAR)
    std = make_slot("S1", Slot.SlotType.STANDARD)
    assert is_slot_eligible(std, vehicle) is True


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
