from django import forms

from vps.lots.models import Lot
from vps.vehicles.models import Vehicle

DATETIME_LOCAL = "%Y-%m-%dT%H:%M"


class ReservationSearchForm(forms.Form):
    """Lot, vehicle and window; used both to search (GET) and to book (POST)."""

    lot = forms.ModelChoiceField(queryset=Lot.objects.none())
    vehicle = forms.ModelChoiceField(queryset=Vehicle.objects.none())
    start = forms.DateTimeField(input_formats=[DATETIME_LOCAL])
    end = forms.DateTimeField(input_formats=[DATETIME_LOCAL])

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = Lot.objects.active()
        self.fields["vehicle"].queryset = Vehicle.objects.filter(owner=user, is_active=True)
