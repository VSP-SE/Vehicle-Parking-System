"""Presentation views for driver parking search and reservation."""



from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from django.views.decorators.http import require_http_methods, require_POST

from vps.lots.models import Lot
from vps.reservations.forms import ReservationConfirmForm
from vps.reservations.models import Reservation
from vps.reservations.services import reserve
from vps.vehicles.models import Vehicle


@login_required
@require_http_methods(["GET", "POST"])
def slot_search(request):
    """Search for suitable parking slots."""
    lots = Lot.objects.all()
    vehicles = Vehicle.objects.filter(
        owner=request.user,
        is_active=True,
    )

    context = {
        "lots": lots,
        "vehicles": vehicles,
        "selected_lot": request.GET.get("lot", ""),
        "selected_vehicle": request.GET.get("vehicle", ""),
        "start": request.GET.get("start", ""),
        "end": request.GET.get("end", ""),
        "slot_count": None,
        "search_error": "",
        "search_url": "",
    }

    # Keep your existing availability-search implementation here.
    # This view should call the search service to validate the window
    # and count available slots when the GET parameters are valid.

    if request.method == "POST":
        form = ReservationConfirmForm(request.POST, user=request.user)

        if form.is_valid():
            try:
                reservation = reserve(
                    driver=request.user,
                    vehicle=form.cleaned_data["vehicle"],
                    lot=form.cleaned_data["lot"],
                    start=form.cleaned_data["start"],
                    end=form.cleaned_data["end"],
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                return redirect(
                    "reservations:confirmation",
                    booking_ref=reservation.booking_ref,
                )

        context["booking_form"] = form

    return render(request, "slots/search.html", context)


@login_required
@require_POST
def confirm_reservation(request):
    """Create a reservation after revalidating the driver's selection."""
    form = ReservationConfirmForm(request.POST, user=request.user)

    if not form.is_valid():
        messages.error(request, "Please correct the booking details.")
        return redirect("reservations:search")

    try:
        reservation = reserve(
            driver=request.user,
            vehicle=form.cleaned_data["vehicle"],
            lot=form.cleaned_data["lot"],
            start=form.cleaned_data["start"],
            end=form.cleaned_data["end"],
        )
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
        return redirect("reservations:search")

    return redirect(
        "reservations:confirmation",
        booking_ref=reservation.booking_ref,
    )


@login_required
def reservation_confirmation(request, booking_ref):
    """Display the booking reference and allocated slot."""
    reservation = get_object_or_404(
        Reservation.objects.select_related("slot", "driver"),
        booking_ref=booking_ref,
        driver=request.user,
    )

    return render(
        request,
        "reservations/confirmation.html",
        {"reservation": reservation},
    )