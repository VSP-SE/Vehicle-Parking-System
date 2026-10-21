"""View permissions with a shared, minimal security audit message."""

import logging
from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from vps.accounts.roles import PERMISSIONS, Function, Role, user_roles

logger = logging.getLogger("vps.security")


def _log_denial(request, roles):
    logger.warning(
        "Role access denied: user_id=%s method=%s path=%s required_roles=%s",
        request.user.pk,
        request.method,
        request.path,
        ", ".join(sorted(roles)),
    )


def role_required(*roles):
    """Allow any specified role; redirect guests and audit authenticated denials."""
    if not roles:
        raise ValueError("At least one role is required")
    required_roles = {Role(role) for role in roles}

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if not user_roles(request.user) & required_roles:
                _log_denial(request, required_roles)
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def function_required(function: Function):
    """Declare access using a row of the shared permission matrix."""
    return role_required(*PERMISSIONS[function])


class HasRole(BasePermission):
    """DRF permission: views declare an iterable of roles in allowed_roles."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        required_roles = {Role(role) for role in getattr(view, "allowed_roles", ())}
        if user_roles(request.user) & required_roles:
            return True
        _log_denial(request, required_roles)
        return False
