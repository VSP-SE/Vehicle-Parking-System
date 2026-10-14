"""Small readers for environment-based Django settings."""

import os

from django.core.exceptions import ImproperlyConfigured


def required_env(name):
    """Read a nonblank required value without exposing it in errors."""
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ImproperlyConfigured(f"{name} must be set to a nonblank value.")
    return value


def env_bool(name, default=False):
    """Accept explicit boolean values and reject accidental typos."""
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean value.")


def env_int(name, default):
    """Read an integer setting with a useful configuration error."""
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer.") from exc


def env_list(name):
    """Read comma-separated values, ignoring whitespace and empty entries."""
    return [value.strip() for value in os.environ.get(name, "").split(",") if value.strip()]
