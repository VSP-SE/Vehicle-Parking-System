"""The allocation module's business rules live here."""
"""Slot eligibility and allocation business rules (FR-ALLOC-01, FR-ALLOC-02)."""

from vps.lots.models import Slot
from vps.vehicles.models import Vehicle


def is_slot_eligible(slot: Slot, vehicle: Vehicle) -> bool:
    """
    Return True if the given slot is allowed for the vehicle under FR-ALLOC-01.
    """
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
    """Return slot types in preferred order for this vehicle (FR-ALLOC-02)."""
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
    From a list of already-eligible and free slots, choose the best one
    according to FR-ALLOC-02:

    1. Preferred slot type first
    2. Lowest distance_rank
    3. Lowest slot code
    """
    if not slots:
        return None

    preference = _type_preference(vehicle)
    # Build a ranking key: (type_priority, distance_rank, code)
    def sort_key(slot: Slot):
        try:
            type_rank = preference.index(slot.slot_type)
        except ValueError:
            type_rank = 999  # should not happen if caller filtered correctly
        return (type_rank, slot.distance_rank, slot.code)

    return min(slots, key=sort_key)