"""Roles and the SRS Appendix B.3 permission matrix.

Each user has exactly one role, stored in ``User.role`` (FR-AUTH-03).
"""

from enum import StrEnum

from vps.accounts.models import User

Role = User.Role


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
    Function.SEARCH: {Role.DRIVER, Role.ATTENDANT, Role.ADMIN},
    Function.OWN_RESERVATIONS: {Role.DRIVER},
    Function.GATE_OPERATIONS: {Role.ATTENDANT},
    Function.CORRECT_TIMES: {Role.ATTENDANT, Role.ADMIN},
    Function.MANAGE_LOTS: {Role.ADMIN},
    Function.MANAGE_STAFF: {Role.ADMIN},
    Function.REPORTS: {Role.ADMIN},
}


def user_roles(user) -> set[Role]:
    """Return the user's role, or nothing for anonymous, inactive or unknown-role users."""
    if not user.is_authenticated or not user.is_active:
        return set()
    try:
        return {Role(user.role)}
    except ValueError:
        return set()


def can(user, function: Function) -> bool:
    """Check a function against the user's role, without privileged bypasses."""
    return bool(user_roles(user) & PERMISSIONS[function])
