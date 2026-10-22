from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models


class LotQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_archived=False)


class Lot(models.Model):
    name = models.CharField(max_length=80)
    address = models.CharField(max_length=200)
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    is_archived = models.BooleanField(default=False)

    objects = LotQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "address"], name="lot_name_address_uniq")
        ]

    def __str__(self):
        return self.name


class Slot(models.Model):
    class SlotType(models.TextChoices):
        STANDARD = "Standard", "Standard"
        TWO_WHEELER = "TwoWheeler", "Two-wheeler"
        EV = "EV", "Electric vehicle"
        ACCESSIBLE = "Accessible", "Accessible"

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="slots")
    code = models.CharField(max_length=10)
    slot_type = models.CharField(max_length=12, choices=SlotType.choices, default=SlotType.STANDARD)
    distance_rank = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["lot_id", "code"]
        constraints = [
            models.UniqueConstraint(fields=["lot", "code"], name="slot_lot_code_uniq"),
            # FR-LOT-02: a positive integer, 1 being nearest to the exit.
            models.CheckConstraint(
                condition=models.Q(distance_rank__gte=1), name="slot_distance_rank_positive"
            ),
        ]
        indexes = [models.Index(fields=["lot", "slot_type"], name="slot_lot_type_idx")]

    def __str__(self):
        return f"{self.lot.name} / {self.code}"


class SlotBlock(models.Model):
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name="blocks")
    period = DateTimeRangeField()
    reason = models.CharField(max_length=200)

    class Meta:
        indexes = [models.Index(fields=["slot"], name="slotblock_slot_idx")]
        constraints = [
            ExclusionConstraint(
                name="slotblock_period_no_overlap",
                expressions=[("slot", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
            ),
        ]

    def __str__(self):
        return f"Block for {self.slot}"


class Tariff(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="tariffs")
    slot_type = models.CharField(max_length=12, choices=Slot.SlotType.choices)
    hourly_rate_inr = models.DecimalField(max_digits=8, decimal_places=2)
    effective_from = models.DateField()

    class Meta:
        ordering = ["lot_id", "slot_type", "-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["lot", "slot_type", "effective_from"], name="tariff_effective_uniq"
            )
        ]
        indexes = [
            models.Index(fields=["lot", "slot_type", "effective_from"], name="tariff_lookup_idx")
        ]

    def __str__(self):
        return f"{self.lot.name}: {self.slot_type} from {self.effective_from}"
