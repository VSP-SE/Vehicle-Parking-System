from django import forms

from vps.accounts.models import User


class AccessiblePermitForm(forms.Form):
    accessible_permit = forms.BooleanField(
        required=False,
        label="Accessible-parking permit holder",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)