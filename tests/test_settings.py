import runpy
from pathlib import Path

import pytest
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_production_settings():
    return runpy.run_path(str(PROJECT_ROOT / "vps" / "settings.py"))


def test_production_settings_require_secret(monkeypatch):
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        load_production_settings()


def test_production_debug_defaults_to_false(monkeypatch):
    monkeypatch.delenv("DJANGO_DEBUG", raising=False)
    assert load_production_settings()["DEBUG"] is False


def test_environment_values_reach_django_settings(monkeypatch):
    values = {
        "DJANGO_SECRET_KEY": "test-only-configured-key",
        "DJANGO_DEBUG": "True",
        "DJANGO_ALLOWED_HOSTS": " localhost, , parking.example.com, ",
        "POSTGRES_DB": "test_parking",
        "POSTGRES_USER": "test_user",
        "POSTGRES_PASSWORD": "test-password",
        "POSTGRES_HOST": "db.example.com",
        "POSTGRES_PORT": "6543",
        "EMAIL_HOST": "smtp.example.com",
        "EMAIL_PORT": "2525",
        "EMAIL_HOST_USER": "test-smtp-user",
        "EMAIL_HOST_PASSWORD": "test-smtp-password",
        "EMAIL_USE_TLS": "True",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    settings = load_production_settings()
    assert settings["SECRET_KEY"] == values["DJANGO_SECRET_KEY"]
    assert settings["DEBUG"] is True
    assert settings["ALLOWED_HOSTS"] == ["localhost", "parking.example.com"]
    assert settings["DATABASES"]["default"] == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": values["POSTGRES_DB"],
        "USER": values["POSTGRES_USER"],
        "PASSWORD": values["POSTGRES_PASSWORD"],
        "HOST": values["POSTGRES_HOST"],
        "PORT": 6543,
    }
    for name in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
        assert settings[name] == values[name]
    assert settings["EMAIL_PORT"] == 2525
    assert settings["EMAIL_USE_TLS"] is True


def test_all_ten_apps_installed(settings):
    for name in (
        "accounts",
        "vehicles",
        "lots",
        "reservations",
        "allocation",
        "gate",
        "billing",
        "reports",
        "audit",
        "notifications",
    ):
        assert apps.is_installed(f"vps.{name}")
        assert apps.get_app_config(name).default_auto_field == "django.db.models.BigAutoField"
    assert apps.is_installed("django.contrib.postgres")
    assert apps.is_installed("rest_framework")
    assert settings.AUTH_USER_MODEL == "accounts.User"
    assert settings.TIME_ZONE == "Asia/Kolkata"
    assert settings.USE_TZ is True


@pytest.mark.parametrize("sqlite_flag", [None, "0", "true", "1"])
def test_sqlite_requires_explicit_opt_in(monkeypatch, sqlite_flag):
    if sqlite_flag is None:
        monkeypatch.delenv("VPS_TEST_SQLITE", raising=False)
    else:
        monkeypatch.setenv("VPS_TEST_SQLITE", sqlite_flag)
    settings = runpy.run_path(str(PROJECT_ROOT / "tests" / "settings.py"))
    expected = "sqlite3" if sqlite_flag == "1" else "postgresql"
    assert settings["DATABASES"]["default"]["ENGINE"] == f"django.db.backends.{expected}"
