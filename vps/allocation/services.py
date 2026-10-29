"""Slot eligibility, choice and retry logic (FR-ALLOC-01, 02, 03)."""

from vps.lots.models import Slot
from vps.vehicles.models import Vehicle

MAX_ALLOCATION_ATTEMPTS = 3


def is_slot_eligible(slot: Slot, vehicle: Vehicle) -> bool:
    """Return True if the slot is allowed for the vehicle (FR-ALLOC-01)."""
    vehicle_type = vehicle.vehicle_type
    slot_type = slot.slot_type
    has_permit = getattr(vehicle.owner, "accessible_permit", False)

    if vehicle_type == Vehicle.VehicleType.TWO_WHEELER:
        return slot_type == Slot.SlotType.TWO_WHEELER

    if vehicle_type == Vehicle.VehicleType.CAR:
        if slot_type == Slot.SlotType.STANDARD:
            return True
        return slot_type == Slot.SlotType.ACCESSIBLE and has_permit

    if vehicle_type == Vehicle.VehicleType.EV:
        return slot_type in (Slot.SlotType.EV, Slot.SlotType.STANDARD)

    return False


def eligible_slot_types(vehicle: Vehicle) -> set[str]:
    """Return the set of slot types allowed for this vehicle."""
    if vehicle.vehicle_type == Vehicle.VehicleType.TWO_WHEELER:
        return {Slot.SlotType.TWO_WHEELER}

    if vehicle.vehicle_type == Vehicle.VehicleType.CAR:
        types = {Slot.SlotType.STANDARD}
        if getattr(vehicle.owner, "accessible_permit", False):
            types.add(Slot.SlotType.ACCESSIBLE)
        return types

    if vehicle.vehicle_type == Vehicle.VehicleType.EV:
        return {Slot.SlotType.EV, Slot.SlotType.STANDARD}

    return set()


def _type_preference(vehicle: Vehicle) -> list[str]:
    """Return slot types in preferred order (FR-ALLOC-02)."""
    if vehicle.vehicle_type == Vehicle.VehicleType.TWO_WHEELER:
        return [Slot.SlotType.TWO_WHEELER]

    if vehicle.vehicle_type == Vehicle.VehicleType.CAR:
        order = [Slot.SlotType.STANDARD]
        if getattr(vehicle.owner, "accessible_permit", False):
            order.append(Slot.SlotType.ACCESSIBLE)
        return order

    if vehicle.vehicle_type == Vehicle.VehicleType.EV:
        return [Slot.SlotType.EV, Slot.SlotType.STANDARD]

    return []


def choose_best_slot(slots: list[Slot], vehicle: Vehicle) -> Slot | None:
    """
    Choose the best slot according to FR-ALLOC-02:
    preferred type → lowest distance_rank → lowest code.
    """
    if not slots:
        return None

    preference = _type_preference(vehicle)

    def sort_key(slot: Slot):
        try:
            type_rank = preference.index(slot.slot_type)
        except ValueError:
            type_rank = 999
        return (type_rank, slot.distance_rank, slot.code)

    return min(slots, key=sort_key)


def allocate_slot_with_retry(
    candidate_slots: list[Slot],
    vehicle: Vehicle,
    try_book,
    max_attempts: int = MAX_ALLOCATION_ATTEMPTS,
) -> Slot | None:
    """
    Try to book a slot, retrying with the next best candidate when a
    concurrent booking wins the race (FR-ALLOC-03).
    """
    remaining = list(candidate_slots)

    for _ in range(max_attempts):
        best = choose_best_slot(remaining, vehicle)
        if best is None:
            return None

        if try_book(best):
            return best

        # Slot was taken – remove it and try the next best
        remaining = [s for s in remaining if s.pk != best.pk]

    return None