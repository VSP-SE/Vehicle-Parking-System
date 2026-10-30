"""Driver parking search, booking and confirmation pages."""

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from vps.accounts.permissions import function_required
from vps.accounts.roles import Function, can
from vps.billing.models import Charge
from vps.reservations.forms import ReservationSearchForm
from vps.reservations.models import Reservation
from vps.reservations.services import cancel_reservation, free_slots, reserve, validate_window

SEARCH_FIELDS = ("lot", "vehicle", "start", "end")


@require_GET
@function_required(Function.SEARCH)
def slot_search(request):
    """FR-SRCH-01: count the slots free for the chosen vehicle and window."""
    searched = any(request.GET.get(name) for name in SEARCH_FIELDS)
    form = ReservationSearchForm(request.GET if searched else None, user=request.user)
    context = {
        "lots": form.fields["lot"].queryset,
        "vehicles": form.fields["vehicle"].queryset,
        "selected_lot": request.GET.get("lot", ""),
        "selected_vehicle": request.GET.get("vehicle", ""),
        "start": request.GET.get("start", ""),
        "end": request.GET.get("end", ""),
        "slot_count": None,
        "search_error": "",
        "search_url": reverse("reservations:search"),
        "confirm_url": "",
    }
    if searched:
        if form.is_valid():
            lot, vehicle, start, end = (form.cleaned_data[name] for name in SEARCH_FIELDS)
            try:
                validate_window(lot, start, end)
            except ValidationError as error:
                context["search_error"] = error.messages[0]
            else:
                context["slot_count"] = len(free_slots(lot, vehicle, start, end))
                if can(request.user, Function.OWN_RESERVATIONS):
                    context["confirm_url"] = reverse("reservations:confirm")
        else:
            context["search_error"] = "Choose a lot, one of your vehicles, a start and an end."
    htmx = request.headers.get("HX-Request") == "true"
    template = "slots/search_result.html" if htmx else "slots/search.html"
    return render(request, template, context)


@require_POST
@function_required(Function.OWN_RESERVATIONS)
def confirm_reservation(request):
    """FR-RES-01: book the searched window, or go back to the search with the reason."""
    form = ReservationSearchForm(request.POST, user=request.user)
    back = (
        reverse("reservations:search")
        + "?"
        + urlencode({name: request.POST.get(name, "") for name in SEARCH_FIELDS})
    )
    if not form.is_valid():
        messages.error(request, "Choose a lot, one of your vehicles, a start and an end.")
        return redirect(back)
    try:
        data = form.cleaned_data
        reservation = reserve(
            request.user, data["vehicle"], data["lot"], data["start"], data["end"]
        )
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
        return redirect(back)
    return redirect("reservations:confirmation", booking_ref=reservation.booking_ref)


@function_required(Function.OWN_RESERVATIONS)
def reservation_confirmation(request, booking_ref):
    """Show the booking reference and slot code (FR-RES-01)."""
    reservation = get_object_or_404(
        Reservation.objects.select_related("slot__lot"),
        booking_ref=booking_ref,
        driver=request.user,
    )
    return render(
        request,
        "reservations/confirmation.html",
        {
            "booking_reference": reservation.booking_ref,
            "slot_code": reservation.slot.code,
            "lot_name": reservation.slot.lot.name,
        },
    )


@require_POST
@function_required(Function.OWN_RESERVATIONS)
def cancel_booking(request, reservation_id):
    """FR-RES-04: Cancel a driver's own reservation."""
    try:
        reservation = cancel_reservation(
            driver=request.user,
            reservation_id=reservation_id,
        )
    except Reservation.DoesNotExist:
        raise Http404("Reservation not found.") from None
    except ValidationError as error:
        for message in error.messages:
            messages.error(request, message)
        return redirect("reservations:search")

    if reservation.charges.filter(kind=Charge.Kind.LATE_CANCEL).exists():
        messages.success(
            request,
            f"Booking {reservation.booking_ref} cancelled. "
            "A late-cancellation charge of Rs 30 has been recorded.",
        )
    else:
        messages.success(request, f"Booking {reservation.booking_ref} cancelled free of charge.")
    return redirect("reservations:search")


@require_GET
@function_required(Function.OWN_RESERVATIONS)
def booking_history(request):
    """FR-RES-06: Show a driver's reservations and charges, newest first."""
    reservations = (
        Reservation.objects.filter(driver=request.user)
        .select_related("slot__lot")
        .prefetch_related(
            Prefetch(
                "charges",
                queryset=Charge.objects.select_related("payment").order_by("id"),
            )
        )
        .order_by("-id")
    )

    paginator = Paginator(reservations, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "reservations/history.html",
        {
            "page_obj": page_obj,
            "reservations": page_obj.object_list,
        },
    )
