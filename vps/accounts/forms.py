"""Forms for Driver registration and e-mail sign-in."""

from django import forms


class RegistrationForm(forms.Form):
    full_name = forms.CharField(min_length=2, max_length=100)
    email = forms.EmailField(max_length=254)
    mobile = forms.RegexField(r"^[6-9][0-9]{9}$", max_length=10)
    password = forms.CharField(strip=False, widget=forms.PasswordInput)


class SignInForm(forms.Form):
    email = forms.EmailField(max_length=254)
    password = forms.CharField(strip=False, widget=forms.PasswordInput)
