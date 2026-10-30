"""Input fields for Gate Attendant walk-in, check-out and time corrections."""

from django import forms

from vps.lots.models import Lot
from vps.reservations.forms import DATETIME_LOCAL
from vps.vehicles.models import Vehicle


class WalkInForm(forms.Form):
    lot = forms.ModelChoiceField(queryset=Lot.objects.active(), label="Parking lot")
    registration_no = forms.CharField(label="Registration number")
    vehicle_type = forms.ChoiceField(choices=Vehicle.VehicleType.choices, label="Vehicle type")


def past_time_field(label, required):
    return forms.DateTimeField(
        label=label,
        required=required,
        input_formats=[DATETIME_LOCAL],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format=DATETIME_LOCAL),
    )


class CheckoutForm(forms.Form):
    """Find an active reservation; after an outage, also take the exit time noted on paper."""

    query = forms.CharField(
        label="Booking reference or vehicle registration",
        max_length=30,
        strip=True,
    )
    exit_time = past_time_field("Exit time from paper record (outage only)", required=False)
    reason = forms.CharField(label="Reason for the past time", max_length=200, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("reason", "").strip() and not cleaned.get("exit_time"):
            self.add_error("exit_time", "Enter the exit time this reason is for.")
        return cleaned


class EntryCorrectionForm(forms.Form):
    """FR-GATE-06: the entry time noted on paper for a vehicle that is still parked."""

    query = forms.CharField(
        label="Booking reference or vehicle registration", max_length=30, strip=True
    )
    entry_time = past_time_field("Entry time from paper record", required=True)
    reason = forms.CharField(label="Reason for the past time", max_length=200, required=False)
