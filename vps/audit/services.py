"""Append-only audit log service (SEC-07)."""

from typing import Any

from django.db import transaction

from vps.audit.models import AuditLog


def log_action(
    *,
    actor=None,
    action: str,
    target: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    """
    Record an audit entry. This is the only way application code should
    write to the audit log.

    The table is treated as append-only: there is no update or delete
    function in this service.
    """
    action = (action or "").strip()
    target = (target or "").strip()

    if not action:
        raise ValueError("action is required")
    if not target:
        raise ValueError("target is required")

    with transaction.atomic():
        entry = AuditLog.objects.create(
            actor=actor,
            action=action,
            target=target,
            before=before,
            after=after,
        )
    return entry