from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import Q

from vps.lots.models import Slot


class Reservation(models.Model):
    class Status(models.TextChoices):
        RESERVED = "Reserved", "Reserved"
        ACTIVE = "Active", "Active"
        COMPLETED = "Completed", "Completed"
        CANCELLED = "Cancelled", "Cancelled"
        EXPIRED = "Expired", "Expired"

    booking_ref = models.CharField(max_length=15, unique=True)
    driver = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="reservations",
        null=True,
        blank=True,
    )
    vehicle_reg_no = models.CharField(max_length=13)
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name="reservations")
    period = DateTimeRangeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RESERVED)
    is_walk_in = models.BooleanField(default=False)
    entry_time = models.DateTimeField(null=True, blank=True)
    exit_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            ExclusionConstraint(
                name="reservation_slot_period_no_overlap",
                expressions=[("slot", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
                condition=Q(status__in=["Reserved", "Active"]),
            ),
        ]
        indexes = [
            models.Index(fields=["status", "slot"], name="reservation_status_slot_idx"),
            models.Index(fields=["driver", "status"], name="reservation_driver_status_idx"),
        ]

    def __str__(self):
        return self.booking_ref
