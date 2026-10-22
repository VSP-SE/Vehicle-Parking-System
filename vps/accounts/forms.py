"""Forms for Driver registration and e-mail sign-in."""

from django import forms
from vps.accounts.models import User


class RegistrationForm(forms.Form):
    full_name = forms.CharField(min_length=2, max_length=100)
    email = forms.EmailField(max_length=254)
    mobile = forms.RegexField(r"^[6-9][0-9]{9}$", max_length=10)
    password = forms.CharField(strip=False, widget=forms.PasswordInput)


class SignInForm(forms.Form):
    email = forms.EmailField(max_length=254)
    password = forms.CharField(strip=False, widget=forms.PasswordInput)

class StaffRegistrationForm(forms.Form):
    full_name = forms.CharField(min_length=2, max_length=100)
    email = forms.EmailField(max_length=254)
    mobile = forms.RegexField(
        regex=r"^[6-9][0-9]{9}$",
        max_length=10,
        error_messages={
            "invalid": "Enter 10 digits, starting with 6, 7, 8 or 9."
        },
    )
    role = forms.ChoiceField(
        choices=[
            (User.Role.ATTENDANT, "Gate Attendant"),
            (User.Role.ADMIN, "Lot Administrator"),
        ]
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput,
    )