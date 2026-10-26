"""Gate Attendant payment pages (FR-GATE-05)."""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from vps.accounts.permissions import function_required
from vps.accounts.roles import Function
from vps.billing.models import Charge, Payment
from vps.billing.services import record_payment, unpaid_charges


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
