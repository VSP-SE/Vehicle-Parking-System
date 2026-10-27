"""Form for the Lot Administrator's accessible-permit page (FR-AUTH-06)."""

from django import forms


class AccessiblePermitForm(forms.Form):
    accessible_permit = forms.BooleanField(
        required=False,
        label="Accessible-parking permit holder",
    )
