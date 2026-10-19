from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    class VehicleType(models.TextChoices):
        CAR = "Car", "Car"
        TWO_WHEELER = "TwoWheeler", "Two-wheeler"
        EV = "EV", "Electric vehicle"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="vehicles"
    )
    registration_no = models.CharField(max_length=13, unique=True)
    vehicle_type = models.CharField(max_length=12, choices=VehicleType.choices)
    nickname = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["registration_no"]
        indexes = [models.Index(fields=["owner", "is_active"], name="vehicle_owner_active_idx")]

    def __str__(self):
        return self.registration_no
