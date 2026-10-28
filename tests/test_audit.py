"""SEC-07 – Append-only audit log (#20)."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from vps.audit.models import AuditLog
from vps.audit.services import log_action

User = get_user_model()
pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(email="admin@example.com", password="password")


def test_log_action_creates_entry(user):
    entry = log_action(
        actor=user,
        action="tariff.change",
        target="lot:1/slot_type:Standard",
        before={"hourly_rate_inr": "30.00"},
        after={"hourly_rate_inr": "40.00"},
    )

    assert entry.pk is not None
    assert entry.actor == user
    assert entry.action == "tariff.change"
    assert entry.target == "lot:1/slot_type:Standard"
    assert entry.before == {"hourly_rate_inr": "30.00"}
    assert entry.after == {"hourly_rate_inr": "40.00"}
    assert entry.at is not None


def test_log_action_allows_null_actor():
    entry = log_action(
        actor=None,
        action="system.cleanup",
        target="reservations",
    )
    assert entry.actor is None
    assert entry.action == "system.cleanup"


def test_log_action_requires_action_and_target():
    with pytest.raises(ValueError, match="action is required"):
        log_action(action="", target="something")

    with pytest.raises(ValueError, match="target is required"):
        log_action(action="test", target="")


def test_saved_entries_cannot_be_edited(user):
    """SEC-07: application code cannot change an audit entry once written."""
    entry = log_action(actor=user, action="test.action", target="t", before={"a": 1})
    entry.before = {"a": 2}
    with pytest.raises(PermissionDenied):
        entry.save()
    with pytest.raises(PermissionDenied):
        AuditLog.objects.filter(pk=entry.pk).update(action="edited")
    entry.refresh_from_db()
    assert (entry.action, entry.before) == ("test.action", {"a": 1})


def test_entries_cannot_be_deleted(user):
    """SEC-07: neither one entry nor a queryset can be deleted."""
    entry = log_action(actor=user, action="test.action", target="t")
    with pytest.raises(PermissionDenied):
        entry.delete()
    with pytest.raises(PermissionDenied):
        AuditLog.objects.all().delete()
    assert AuditLog.objects.filter(pk=entry.pk).exists()
