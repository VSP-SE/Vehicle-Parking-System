"""Group-backed roles and the SRS Appendix B.3 permission matrix."""

from enum import StrEnum


class Role(StrEnum):
    DRIVER = "Driver"
    GATE_ATTENDANT = "Gate Attendant"
    LOT_ADMINISTRATOR = "Lot Administrator"


class Function(StrEnum):
    # Registration and own-vehicle management share the first matrix row.
    MANAGE_OWN_VEHICLES = "manage_own_vehicles"
    SEARCH = "search"
    OWN_RESERVATIONS = "own_reservations"
    GATE_OPERATIONS = "gate_operations"
    CORRECT_TIMES = "correct_times"
    MANAGE_LOTS = "manage_lots"
    MANAGE_STAFF = "manage_staff"
    REPORTS = "reports"


PERMISSIONS: dict[Function, set[Role]] = {
    Function.MANAGE_OWN_VEHICLES: {Role.DRIVER},
    Function.SEARCH: {Role.DRIVER, Role.GATE_ATTENDANT, Role.LOT_ADMINISTRATOR},
    Function.OWN_RESERVATIONS: {Role.DRIVER},
    Function.GATE_OPERATIONS: {Role.GATE_ATTENDANT},
    Function.CORRECT_TIMES: {Role.GATE_ATTENDANT, Role.LOT_ADMINISTRATOR},
    Function.MANAGE_LOTS: {Role.LOT_ADMINISTRATOR},
    Function.MANAGE_STAFF: {Role.LOT_ADMINISTRATOR},
    Function.REPORTS: {Role.LOT_ADMINISTRATOR},
}


def user_roles(user) -> set[Role]:
    """Return recognized groups only for authenticated, active users."""
    if not user.is_authenticated or not user.is_active:
        return set()
    return {
        Role(name)
        for name in user.groups.filter(name__in=Role).values_list("name", flat=True)
    }


def can(user, function: Function) -> bool:
    """Check a function against group membership, without privileged bypasses."""
    return bool(user_roles(user) & PERMISSIONS[function])
