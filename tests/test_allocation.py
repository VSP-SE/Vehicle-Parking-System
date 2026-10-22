"""FR-ALLOC-01 + FR-ALLOC-02 + FR-ALLOC-03 – Slot eligibility, choice and retry."""

from datetime import time

import pytest

from vps.accounts.models import User
from vps.allocation.services import (
    allocate_slot_with_retry,
    choose_best_slot,
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


# ---------- Eligibility (#36) ----------

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


# ---------- Deterministic choice (#37) ----------

def test_choose_best_slot_prefers_type_then_rank_then_code(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.EV)
    s_far = make_slot("S9", Slot.SlotType.STANDARD, rank=5)
    e_far = make_slot("E9", Slot.SlotType.EV, rank=5)
    e_near = make_slot("E1", Slot.SlotType.EV, rank=1)
    s_near = make_slot("S1", Slot.SlotType.STANDARD, rank=1)
    e_near_b = make_slot("E2", Slot.SlotType.EV, rank=1)

    best = choose_best_slot([s_far, e_far, e_near_b, s_near, e_near], vehicle)
    assert best == e_near


def test_choose_best_slot_empty_list_returns_none(make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.CAR)
    assert choose_best_slot([], vehicle) is None


# ---------- Retry logic (#38) ----------

def test_allocate_succeeds_on_first_try(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.EV)
    e1 = make_slot("E1", Slot.SlotType.EV, rank=1)
    e2 = make_slot("E2", Slot.SlotType.EV, rank=2)

    def try_book(slot):
        return True

    result = allocate_slot_with_retry([e2, e1], vehicle, try_book)
    assert result == e1


def test_allocate_retries_when_first_slot_is_taken(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.EV)
    e1 = make_slot("E1", Slot.SlotType.EV, rank=1)
    e2 = make_slot("E2", Slot.SlotType.EV, rank=2)

    attempts = []

    def try_book(slot):
        attempts.append(slot.code)
        return slot.code == "E2"

    result = allocate_slot_with_retry([e1, e2], vehicle, try_book)
    assert result == e2
    assert attempts == ["E1", "E2"]


def test_allocate_gives_up_after_three_attempts(make_slot, make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.CAR)
    slots = [
        make_slot("S1", Slot.SlotType.STANDARD, rank=1),
        make_slot("S2", Slot.SlotType.STANDARD, rank=2),
        make_slot("S3", Slot.SlotType.STANDARD, rank=3),
        make_slot("S4", Slot.SlotType.STANDARD, rank=4),
    ]

    attempts = []

    def try_book(slot):
        attempts.append(slot.code)
        return False

    result = allocate_slot_with_retry(slots, vehicle, try_book)
    assert result is None
    assert attempts == ["S1", "S2", "S3"]


def test_allocate_returns_none_when_no_candidates(make_vehicle):
    vehicle = make_vehicle(Vehicle.VehicleType.CAR)

    def try_book(slot):
        return True

    assert allocate_slot_with_retry([], vehicle, try_book) is None