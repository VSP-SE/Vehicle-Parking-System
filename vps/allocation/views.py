# vps/allocation/views.py

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.timezone import is_naive, make_aware
from django.views.decorators.http import require_GET

from vps.accounts.permissions import function_required
from vps.accounts.roles import Function
from vps.allocation.forms import AvailabilitySearchForm
from vps.allocation.search import (
    SearchWindowError,
    search_available_slots,
)


@require_GET
@login_required
@function_required(Function.SEARCH)
def search(request):
    form = AvailabilitySearchForm(
        request.GET if request.GET else None,
        user=request.user,
    )

    context = {
        "form": form,
        "lots": form.fields["lot"].queryset,
        "vehicles": form.fields["vehicle"].queryset,
        "search_url": request.path,
        "slot_count": None,
        "search_error": "",
        "selected_lot": request.GET.get("lot", ""),
        "selected_vehicle": request.GET.get("vehicle", ""),
        "start": request.GET.get("start", ""),
        "end": request.GET.get("end", ""),
    }

    if request.GET and form.is_valid():
        lot = form.cleaned_data["lot"]
        vehicle = form.cleaned_data["vehicle"]
        start = form.cleaned_data["start"]
        end = form.cleaned_data["end"]

        # Interpret browser-local datetime values in Django's current timezone.
        if is_naive(start):
            start = make_aware(start, timezone.get_current_timezone())
        if is_naive(end):
            end = make_aware(end, timezone.get_current_timezone())

        try:
            context["slot_count"] = search_available_slots(
                lot=lot,
                vehicle=vehicle,
                start=start,
                end=end,
            )
        except SearchWindowError as exc:
            context["search_error"] = str(exc)

    elif request.GET:
        context["search_error"] = "Correct the highlighted search fields."

    template = (
        "slots/search_result.html"
        if request.headers.get("HX-Request") == "true"
        else "slots/search.html"
    )

    return render(request, template, context)