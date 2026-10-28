"""Input fields for Gate Attendant walk-in registration."""

from django import forms

from vps.lots.models import Lot
from vps.vehicles.models import Vehicle


class WalkInForm(forms.Form):
    lot = forms.ModelChoiceField(queryset=Lot.objects.active(), label="Parking lot")
    registration_no = forms.CharField(label="Registration number")
    vehicle_type = forms.ChoiceField(choices=Vehicle.VehicleType.choices, label="Vehicle type")


class CheckoutForm(forms.Form):
    """Find an active reservation by booking reference or registration number."""

    query = forms.CharField(
        label="Booking reference or vehicle registration",
        max_length=30,
        strip=True,
    )
