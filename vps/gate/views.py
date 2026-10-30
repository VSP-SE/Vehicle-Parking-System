"""Gate Attendant walk-in, check-out, correction and payment pages (FR-GATE-03 to 06)."""

from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from vps.accounts.permissions import function_required, role_required
from vps.accounts.roles import PERMISSIONS, Function, can
from vps.billing.models import Charge, Payment
from vps.billing.services import record_payment, unpaid_charges
from vps.gate.forms import CheckoutForm, EntryCorrectionForm, WalkInForm
from vps.gate.services import (
    CHECKOUT_GRACE,
    _billable_hours,
    _hourly_rate,
    check_in_vehicle,
    checkout_vehicle,
    correct_entry_time,
    register_walk_in,
)
from vps.lots.models import Lot
from vps.reservations.models import Reservation


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


@function_required(Function.GATE_OPERATIONS)
@require_http_methods(["GET", "POST"])
def checkout(request):
    """FR-GATE-04: check out an active vehicle and display its receipt."""
    form = CheckoutForm(request.POST if request.method == "POST" else None)

    if request.method == "POST" and form.is_valid():
        try:
            reservation = checkout_vehicle(
                query=form.cleaned_data["query"],
                attendant=request.user,
                exit_time=form.cleaned_data["exit_time"],
                reason=form.cleaned_data["reason"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect(
                "gate:receipt",
                booking_ref=reservation.booking_ref,
            )

    return render(request, "gate/checkout.html", {"form": form})


@function_required(Function.GATE_OPERATIONS)
@require_http_methods(["GET", "POST"])
def correct_entry(request):
    """FR-GATE-06: enter the paper entry time for a vehicle parked during an outage."""
    form = EntryCorrectionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            reservation = correct_entry_time(request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(
                request,
                f"Entry time for {reservation.booking_ref} corrected to "
                f"{timezone.localtime(reservation.entry_time):%d %b %Y %H:%M}.",
            )
            return redirect("gate:correct_entry")
    return render(request, "gate/correct_entry.html", {"form": form})


def _receipt_context(reservation):
    """FR-BILL-04: itemised charges, billable time and payment state of a completed stay."""
    charges = list(reservation.charges.select_related("payment").order_by("id"))
    total = sum((charge.amount_inr for charge in charges), Decimal("0.00"))
    payments = [charge.payment for charge in charges if hasattr(charge, "payment")]
    paid_total = sum((payment.charge.amount_inr for payment in payments), Decimal("0.00"))

    parking_end = reservation.exit_time
    if not reservation.is_walk_in:
        parking_end = min(parking_end, reservation.period.upper)
    parking_hours = _billable_hours(parking_end - reservation.entry_time, minimum_one_hour=True)
    overstay_hours = Decimal("0.0")
    if (
        not reservation.is_walk_in
        and reservation.exit_time > reservation.period.upper + CHECKOUT_GRACE
    ):
        overstay_hours = _billable_hours(
            reservation.exit_time - (reservation.period.upper + CHECKOUT_GRACE)
        )

    if paid_total == total:
        payment_status = "Paid"
    elif paid_total:
        payment_status = "Partially paid"
    else:
        payment_status = "Unpaid"
    return {
        "reservation": reservation,
        "parking_hours": parking_hours,
        "overstay_hours": overstay_hours,
        "billable_duration": f"{parking_hours + overstay_hours} hours",
        "hourly_rate": _hourly_rate(reservation),
        "charges": charges,
        "total": total,
        "total_amount": total,
        "paid_total": paid_total,
        "balance_due": total - paid_total,
        "payment": max(payments, key=lambda payment: payment.paid_at, default=None),
        "payment_status": payment_status,
    }


def _completed_reservation(booking_ref):
    return get_object_or_404(
        Reservation.objects.select_related("slot__lot"),
        booking_ref=booking_ref,
        status=Reservation.Status.COMPLETED,
    )


@function_required(Function.GATE_OPERATIONS)
def receipt(request, booking_ref):
    """Display the itemised checkout receipt."""
    reservation = _completed_reservation(booking_ref)
    return render(request, "gate/receipt.html", _receipt_context(reservation))


@role_required(*PERMISSIONS[Function.GATE_OPERATIONS], *PERMISSIONS[Function.OWN_RESERVATIONS])
def printable_receipt(request, booking_ref):
    """FR-BILL-04: the printable receipt, for attendants and for the Driver who booked."""
    reservation = _completed_reservation(booking_ref)
    if not can(request.user, Function.GATE_OPERATIONS) and reservation.driver_id != request.user.pk:
        raise Http404("Receipt not found.")
    return render(request, "billing/receipt.html", _receipt_context(reservation))


def _dashboard(request, **context):
    """FR-GATE (#47): one console for check-in, check-out and walk-ins."""
    return render(
        request,
        "gate/dashboard.html",
        {
            "checkin_url": reverse("gate:checkin"),
            "checkout_url": reverse("gate:dashboard_checkout"),
            "walkin_url": reverse("gate:dashboard_walk_in"),
            "lots": Lot.objects.active(),
            **context,
        },
    )


@function_required(Function.GATE_OPERATIONS)
@require_GET
def dashboard(request):
    """Display the Gate Attendant dashboard."""
    return _dashboard(request)


@function_required(Function.GATE_OPERATIONS)
@require_POST
def dashboard_checkin(request):
    """FR-GATE-01/02: check in a reserved vehicle from the dashboard."""
    try:
        reservation = check_in_vehicle(request.POST.get("reference", ""), request.user)
    except ValidationError as error:
        return _dashboard(request, gate_error=" ".join(error.messages))
    message = f"Checked in {reservation.vehicle_reg_no} at slot {reservation.slot.code}."
    if reservation.reallocated_from:
        message += (
            f" Slot {reservation.reallocated_from} is still occupied. "
            f"Park in slot {reservation.slot.code}."
        )
    return _dashboard(request, gate_message=message)


@function_required(Function.GATE_OPERATIONS)
@require_POST
def dashboard_checkout(request):
    """FR-GATE-04: check out a vehicle from the dashboard and show its receipt."""
    try:
        reservation = checkout_vehicle(request.POST.get("reference", ""), request.user)
    except ValidationError as error:
        return _dashboard(request, gate_error=" ".join(error.messages))
    return redirect("gate:receipt", booking_ref=reservation.booking_ref)


@function_required(Function.GATE_OPERATIONS)
@require_POST
def dashboard_walk_in(request):
    """FR-GATE-03: register a walk-in vehicle from the dashboard."""
    form = WalkInForm(request.POST)
    if form.is_valid():
        try:
            reservation = register_walk_in(request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return _dashboard(
                request,
                gate_message=(
                    f"Walk-in {reservation.vehicle_reg_no} parked in {reservation.slot.code}."
                ),
            )
    errors = " ".join(error for field_errors in form.errors.values() for error in field_errors)
    return _dashboard(request, gate_error=errors)
