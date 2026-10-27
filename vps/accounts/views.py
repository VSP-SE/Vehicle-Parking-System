"""Authentication pages and role-specific home routing."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST, require_safe, login_required

from vps.accounts import services
from vps.accounts.forms import RegistrationForm, SignInForm, StaffRegistrationForm
from vps.accounts.models import User
from vps.accounts.permissions import role_required
from vps.accounts.roles import Role, user_roles


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
    form = StaffRegistrationForm(
        request.POST if request.method == "POST" else None
    )

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

@login_required
@require_http_methods(["GET", "POST"])
def manage_accessible_permit(request, user_id):
    if Role.ADMIN not in user_roles(request.user):
        raise PermissionDenied

    driver = get_object_or_404(
        User,
        pk=user_id,
        role=User.Role.DRIVER,
    )

    if request.method == "POST":
        driver.accessible_permit = (
            request.POST.get("accessible_permit") == "on"
        )
        driver.save(update_fields=["accessible_permit"])

        messages.success(
            request,
            f"Accessible-parking permit status updated for {driver.email}.",
        )
        return redirect("accounts:manage_accessible_permit", user_id=driver.pk)

    return render(
        request,
        "accounts/manage_accessible_permit.html",
        {"driver": driver},
    )