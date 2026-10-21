from django.conf import settings
from django.db import models


class Charge(models.Model):
    class Kind(models.TextChoices):
        PARKING = "Parking", "Parking"
        OVERSTAY = "Overstay", "Overstay"
        LATE_CANCEL = "LateCancel", "Late cancellation"
        NO_SHOW = "NoShow", "No-show"

    reservation = models.ForeignKey(
        "reservations.Reservation", on_delete=models.PROTECT, related_name="charges"
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    amount_inr = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=["reservation", "kind"], name="charge_res_kind_idx")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_inr__gte=0), name="charge_amount_nonnegative"
            )
        ]

    def __str__(self):
        return f"{self.kind}: INR {self.amount_inr}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "Cash", "Cash"
        UPI = "UPI", "UPI"
        CARD = "Card", "Card"

    charge = models.OneToOneField(Charge, on_delete=models.PROTECT, related_name="payment")
    method = models.CharField(max_length=4, choices=Method.choices)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_payments"
    )
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]

    def __str__(self):
        return f"Payment for charge {self.charge_id}"
