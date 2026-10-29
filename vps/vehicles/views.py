"""Driver vehicle registration page."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from vps.accounts.permissions import function_required
from vps.accounts.roles import Function
from vps.billing.services import unpaid_total
from vps.vehicles import services
from vps.vehicles.forms import VehicleForm
from vps.vehicles.models import Vehicle


@function_required(Function.MANAGE_OWN_VEHICLES)
@require_http_methods(["GET", "POST"])
def register(request):
    form = VehicleForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            services.add_vehicle(request.user, **form.cleaned_data)
        except ValidationError as error:
            for field, errors in error.error_dict.items():
                form.add_error(None if field == "__all__" else field, errors)
        else:
            messages.success(request, "Vehicle registered successfully.")
            return redirect("vehicles:register")
    vehicles = Vehicle.objects.filter(owner=request.user, is_active=True)
    count = vehicles.count()
    return render(
        request,
        "vehicles/register.html",
        {
            "form": form,
            "vehicles": vehicles,
            "vehicle_count": count,
            "vehicle_limit_reached": count >= 5,
            "vehicle_error": form.non_field_errors(),
            "unpaid_total": unpaid_total(request.user),
            **{
                field: form[field].value()
                for field in ("registration_no", "vehicle_type", "nickname")
            },
        },
    )
