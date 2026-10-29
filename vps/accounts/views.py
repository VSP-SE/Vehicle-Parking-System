"""Authentication pages and role-specific home routing."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import views as auth_views
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from vps.accounts import services
from vps.accounts.forms import RegistrationForm, SignInForm, StaffRegistrationForm
from vps.accounts.models import User
from vps.accounts.permissions import role_required
from vps.accounts.permit_forms import AccessiblePermitForm


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            user = services.register_driver(**form.cleaned_data)
        except ValidationError as error:
            for field, errors in error.error_dict.items():
                form.add_error(field, errors)
        else:
            login(request, user)
            return redirect(settings.LOGIN_REDIRECT_URL)
    return render(
        request,
        "accounts/register.html",
        {
            "form": form,
            **{field: form[field].value() for field in ("full_name", "email", "mobile")},
        },
    )


@require_http_methods(["GET", "POST"])
def sign_in(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = SignInForm(request.POST if request.method == "POST" else None)
    next_url = request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = ""
    if request.method == "POST" and form.is_valid():
        user = authenticate(request, **form.cleaned_data)
        if user is not None:
            login(request, user)
            return redirect(next_url or settings.LOGIN_REDIRECT_URL)
    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "email": form["email"].value(),
            "next": next_url,
            "login_error": "Invalid e-mail or password" if request.method == "POST" else "",
        },
    )


@require_POST
def sign_out(request):
    logout(request)
    return redirect(settings.LOGOUT_REDIRECT_URL)


@require_safe
def home(request):
    if not request.user.is_authenticated:
        return redirect(settings.LOGIN_URL)
    destinations = {
        User.Role.DRIVER: "/vehicles/",
        User.Role.ADMIN: "/lots/",
        User.Role.ATTENDANT: "/reservations/search/",
    }
    if not request.user.is_active or request.user.role not in destinations:
        raise PermissionDenied
    return redirect(destinations[request.user.role])


@role_required(User.Role.ADMIN)
@require_http_methods(["GET", "POST"])
def create_staff(request):
    form = StaffRegistrationForm(request.POST if request.method == "POST" else None)

    if request.method == "POST" and form.is_valid():
        try:
            staff = services.create_staff(**form.cleaned_data)
        except ValidationError as error:
            for field, errors in error.error_dict.items():
                form.add_error(field, errors)
        else:
            from django.contrib import messages

            messages.success(
                request,
                f"Staff account created for {staff.email}.",
            )
            return redirect("accounts:create_staff")

    return render(
        request,
        "accounts/create_staff.html",
        {"form": form},
    )


@role_required(User.Role.ADMIN)
@require_safe
def drivers(request):
    """FR-AUTH-06: find Drivers by e-mail to check their permit status."""
    query = request.GET.get("q", "").strip()
    found = User.objects.filter(role=User.Role.DRIVER).order_by("email")
    if query:
        found = found.filter(email__icontains=query)
    return render(request, "accounts/drivers.html", {"drivers": found, "q": query})


@role_required(User.Role.ADMIN)
@require_http_methods(["GET", "POST"])
def manage_accessible_permit(request, user_id):
    """FR-AUTH-06: mark a Driver as a permit holder after an offline check."""
    driver = get_object_or_404(User, pk=user_id, role=User.Role.DRIVER)
    form = AccessiblePermitForm(
        request.POST if request.method == "POST" else None,
        initial={"accessible_permit": driver.accessible_permit},
    )
    if form.is_valid():
        services.set_accessible_permit(request.user, driver, form.cleaned_data["accessible_permit"])
        messages.success(request, f"Accessible-parking permit status updated for {driver.email}.")
        return redirect("accounts:manage_accessible_permit", user_id=driver.pk)
    return render(
        request, "accounts/manage_accessible_permit.html", {"driver": driver, "form": form}
    )


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.html"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
