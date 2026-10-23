from django import forms

from vps.lots.models import Lot
from vps.vehicles.models import Vehicle


class ReservationConfirmForm(forms.Form):
    lot = forms.ModelChoiceField(queryset=Lot.objects.none())
    vehicle = forms.ModelChoiceField(queryset=Vehicle.objects.none())
    start = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    end = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = Lot.objects.all()
        self.fields["vehicle"].queryset = Vehicle.objects.filter(
            owner=user,
            is_active=True,
        )