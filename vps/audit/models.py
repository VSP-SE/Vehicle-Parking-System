from django.conf import settings
from django.db import models


class AuditLog(models.Model):
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

    class Meta:
        ordering = ["-at", "-id"]
        indexes = [
            models.Index(fields=["target", "at"], name="audit_target_at_idx"),
            models.Index(fields=["actor", "at"], name="audit_actor_at_idx"),
        ]

    def __str__(self):
        return f"{self.action} - {self.target} at {self.at}"
