"""Server-rendered lot details form."""

from decimal import Decimal
from typing import ClassVar

from django import forms

from vps.lots.models import Lot, Slot
from vps.lots.services import validate_hours, validate_unique_lot


class LotForm(forms.ModelForm):
    class Meta:
        model = Lot
        fields = ("name", "address", "opens_at", "closes_at")
        labels: ClassVar = {"opens_at": "Opening time", "closes_at": "Closing time"}
        widgets: ClassVar = {
            "opens_at": forms.TimeInput(format="%H:%M", attrs={"placeholder": "HH:MM"}),
            "closes_at": forms.TimeInput(format="%H:%M", attrs={"placeholder": "HH:MM"}),
        }
        error_messages: ClassVar = {
            "name": {"required": "Enter a name for the parking lot."},
            "address": {"required": "Enter an address for the parking lot."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("opens_at", "closes_at"):
            self.fields[name].input_formats = ["%H:%M"]
            self.fields[name].help_text = "Use 24-hour HH:MM format, for example 06:00 or 23:00."
            self.fields[name].error_messages.update(
                {
                    "required": "Enter a time in 24-hour HH:MM format, for example 06:00.",
                    "invalid": "Enter a time in 24-hour HH:MM format, for example 06:00.",
                }
            )

    def clean(self):
        cleaned = super().clean()
        validate_hours(cleaned.get("opens_at"), cleaned.get("closes_at"))
        # Raising on the name field here also stops Django adding its generic
        # form-level message for the same unique constraint.
        validate_unique_lot(cleaned.get("name"), cleaned.get("address"), self.instance.pk)
        return cleaned


class TariffForm(forms.Form):
    """FR-BILL-01: an hourly rate for one lot and slot type from a given date."""

    lot_id = forms.ModelChoiceField(
        queryset=Lot.objects.active(),
        label="Parking lot",
        empty_label="Select a parking lot",
    )
    slot_type = forms.ChoiceField(
        choices=Slot.SlotType.choices,
        label="Slot type",
    )
    hourly_rate_inr = forms.DecimalField(
        label="Hourly rate (₹)",
        min_value=Decimal("0.01"),
        max_digits=8,
        decimal_places=2,
    )
    effective_from = forms.DateField(
        label="Effective from",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
