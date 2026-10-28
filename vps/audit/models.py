from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models

APPEND_ONLY = "Audit entries cannot be changed or deleted (SEC-07)."


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionDenied(APPEND_ONLY)

    def delete(self):
        raise PermissionDenied(APPEND_ONLY)


class AuditLog(models.Model):
    """SEC-07: append-only; entries can be created but never edited or deleted."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=50)
    target = models.CharField(max_length=100)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [
            models.Index(fields=["target", "at"], name="audit_target_at_idx"),
            models.Index(fields=["actor", "at"], name="audit_actor_at_idx"),
        ]

    def __str__(self):
        return f"{self.action} - {self.target} at {self.at}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionDenied(APPEND_ONLY)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied(APPEND_ONLY)
