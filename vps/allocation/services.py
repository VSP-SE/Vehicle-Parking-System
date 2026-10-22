"""Slot eligibility and allocation business rules (FR-ALLOC-01)."""

from vps.lots.models import Slot
from vps.vehicles.models import Vehicle


def is_slot_eligible(slot: Slot, vehicle: Vehicle) -> bool:
    """
    Return True if the given slot is allowed for the vehicle under FR-ALLOC-01.

    Rules:
    - Two-wheeler  → only TwoWheeler slots
    - Car          → Standard slots, plus Accessible if the owner has a permit
    - EV           → EV slots and Standard slots
    """
    vehicle_type = vehicle.vehicle_type
    slot_type = slot.slot_type
    has_permit = getattr(vehicle.owner, "accessible_permit", False)

    if vehicle_type == Vehicle.VehicleType.TWO_WHEELER:
        return slot_type == Slot.SlotType.TWO_WHEELER

    if vehicle_type == Vehicle.VehicleType.CAR:
        if slot_type == Slot.SlotType.STANDARD:
            return True
        if slot_type == Slot.SlotType.ACCESSIBLE and has_permit:
            return True
        return False

    if vehicle_type == Vehicle.VehicleType.EV:
        return slot_type in (Slot.SlotType.EV, Slot.SlotType.STANDARD)

    # Unknown vehicle type is never eligible
    return False


def eligible_slot_types(vehicle: Vehicle) -> set[str]:
    """
    Return the set of slot types that are allowed for this vehicle.
    Useful for filtering querysets.
    """
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