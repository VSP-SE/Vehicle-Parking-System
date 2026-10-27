"""Gate Attendant walk-in and payment pages (FR-GATE-03, 05)."""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from vps.accounts.permissions import function_required
from vps.accounts.roles import Function
from vps.billing.models import Charge, Payment
from vps.billing.services import record_payment, unpaid_charges
from vps.gate.forms import WalkInForm
from vps.gate.services import register_walk_in


@function_required(Function.GATE_OPERATIONS)
@require_GET
def payments(request):
    """FR-GATE-05: search for charges still awaiting payment."""
    query = request.GET.get("q", "")
    return render(
        request,
        "gate/payments.html",
        {"q": query, "charges": unpaid_charges(query), "methods": Payment.Method.choices},
    )


@function_required(Function.GATE_OPERATIONS)
@require_POST
def pay_charge(request, charge_id):
    """FR-GATE-05: record payment and return to the same search with the result."""
    charge = get_object_or_404(Charge.objects.select_related("reservation"), pk=charge_id)
    back = reverse("gate:payments") + "?" + urlencode({"q": request.POST.get("q", "")})
    try:
        payment = record_payment(request.user, charge, request.POST.get("method", ""))
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
    else:
        messages.success(
            request,
            f"Payment of Rs {payment.charge.amount_inr:.2f} recorded for "
            f"{payment.charge.reservation.booking_ref}",
        )
    return redirect(back)


@function_required(Function.GATE_OPERATIONS)
@require_http_methods(["GET", "POST"])
def walk_in(request):
    """FR-GATE-03: register an arrival and show its slot and booking reference."""
    form = WalkInForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            reservation = register_walk_in(request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(
                request,
                f"Walk-in {reservation.vehicle_reg_no} parked in "
                f"{reservation.slot.code} ({reservation.booking_ref}).",
            )
            return redirect("gate:walk_in")
    return render(request, "gate/walk_in.html", {"form": form})
