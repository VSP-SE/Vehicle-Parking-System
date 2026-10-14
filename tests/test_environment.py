import pytest
from django.core.exceptions import ImproperlyConfigured


def test_missing_secret_key(monkeypatch):
    from vps.environment import required_env

    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        required_env("DJANGO_SECRET_KEY")


def test_debug_defaults_to_false(monkeypatch):
    from vps.environment import env_bool

    monkeypatch.delenv("DJANGO_DEBUG", raising=False)
    assert env_bool("DJANGO_DEBUG") is False


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_secret_key_is_rejected(monkeypatch, value):
    from vps.environment import required_env

    monkeypatch.setenv("DJANGO_SECRET_KEY", value)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        required_env("DJANGO_SECRET_KEY")


def test_secret_key_is_read_from_environment(monkeypatch):
    from vps.environment import required_env

    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret")
    assert required_env("DJANGO_SECRET_KEY") == "test-secret"


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_true_boolean_values(monkeypatch, value):
    from vps.environment import env_bool

    monkeypatch.setenv("DJANGO_DEBUG", value)
    assert env_bool("DJANGO_DEBUG") is True


@pytest.mark.parametrize("value", ["0", "false", "NO", " off "])
def test_false_boolean_values(monkeypatch, value):
    from vps.environment import env_bool

    monkeypatch.setenv("DJANGO_DEBUG", value)
    assert env_bool("DJANGO_DEBUG") is False


@pytest.mark.parametrize("value", ["", "tru", "2"])
def test_invalid_boolean_values(monkeypatch, value):
    from vps.environment import env_bool

    monkeypatch.setenv("DJANGO_DEBUG", value)
    with pytest.raises(ImproperlyConfigured, match="DJANGO_DEBUG must be a boolean"):
        env_bool("DJANGO_DEBUG")


def test_invalid_integer_value(monkeypatch):
    from vps.environment import env_int

    monkeypatch.setenv("EMAIL_PORT", "invalid")
    with pytest.raises(ImproperlyConfigured, match="EMAIL_PORT must be an integer"):
        env_int("EMAIL_PORT", 587)


def test_integer_default(monkeypatch):
    from vps.environment import env_int

    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    assert env_int("POSTGRES_PORT", 5432) == 5432


def test_missing_allowed_hosts_is_empty(monkeypatch):
    from vps.environment import env_list

    monkeypatch.delenv("DJANGO_ALLOWED_HOSTS", raising=False)
    assert env_list("DJANGO_ALLOWED_HOSTS") == []
