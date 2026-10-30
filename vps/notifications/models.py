from django.db import models


class ReservationNotification(models.Model):
    class Event(models.TextChoices):
        CREATED = "created", "Booking created"
        CANCELLED = "cancelled", "Booking cancelled"
        MOVED = "moved", "Booking moved"
        EXPIRED = "expired", "Booking expired"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    reservation = models.ForeignKey(
        "reservations.Reservation",
        on_delete=models.PROTECT,
        related_name="notifications",
    )
    event = models.CharField(max_length=20, choices=Event.choices)
    event_key = models.CharField(max_length=255, unique=True)

    recipient_email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="notification_pending_idx",
            ),
        ]

    def __str__(self):
        return f"{self.event} - {self.reservation.booking_ref}"
