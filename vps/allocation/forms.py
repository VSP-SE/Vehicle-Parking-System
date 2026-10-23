# vps/allocation/forms.py

from django import forms

from vps.lots.models import Lot
from vps.vehicles.models import Vehicle


class AvailabilitySearchForm(forms.Form):
    lot = forms.ModelChoiceField(
        queryset=Lot.objects.none(),
        empty_label="Choose a parking lot",
    )
    vehicle = forms.ModelChoiceField(
        queryset=Vehicle.objects.none(),
        empty_label="Choose your vehicle",
    )
    start = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )
    end = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lot"].queryset = Lot.objects.all()
        self.fields["vehicle"].queryset = Vehicle.objects.filter(
            owner=user
        )