"""Vehicle input form; services enforce the registration rules."""

from django import forms
from django.core.exceptions import ValidationError

from vps.vehicles.models import Vehicle
from vps.vehicles.services import normalise_registration, validate_registration


class VehicleForm(forms.Form):
    registration_no = forms.CharField()
    vehicle_type = forms.ChoiceField(choices=Vehicle.VehicleType.choices)
    nickname = forms.CharField(max_length=30, required=False)

    def clean_registration_no(self):
        number = normalise_registration(self.cleaned_data["registration_no"])
        try:
            validate_registration(number)
        except ValidationError as error:
            raise ValidationError(error.messages) from error
        return number
