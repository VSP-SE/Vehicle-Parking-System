"""Administrator lot pages; business rules belong to services."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from vps.accounts.permissions import function_required
from vps.accounts.roles import Function
from vps.lots import services
from vps.lots.forms import LotForm
from vps.lots.models import Lot


@function_required(Function.MANAGE_LOTS)
@require_safe
def lot_list(request):
    archived = request.GET.get("archived") == "1"
    lots = Lot.objects.filter(is_archived=True) if archived else Lot.objects.active()
    return render(request, "lots/list.html", {
        "lots": lots.annotate(slot_count=Count("slots")), "archived": archived,
    })


def _lot_form(request, lot=None):
    form = LotForm(request.POST if request.method == "POST" else None, instance=lot)
    if request.method == "POST" and form.is_valid():
        try:
            if lot is None:
                services.create_lot(**form.cleaned_data)
            else:
                services.update_lot(lot, **form.cleaned_data)
        except ValidationError as error:
            if hasattr(error, "error_dict"):
                for field, errors in error.error_dict.items():
                    form.add_error(field, errors)
            else:
                form.add_error(None, error)
        else:
            action = "created" if lot is None else "updated"
            messages.success(request, f"Parking lot {action} successfully.")
            return redirect("lots:list")
    return render(request, "lots/form.html", {"form": form, "lot": lot})


@function_required(Function.MANAGE_LOTS)
def lot_create(request):
    return _lot_form(request)


@function_required(Function.MANAGE_LOTS)
def lot_edit(request, pk):
    return _lot_form(request, get_object_or_404(Lot, pk=pk))


@function_required(Function.MANAGE_LOTS)
@require_POST
def lot_archive(request, pk):
    services.archive_lot(get_object_or_404(Lot, pk=pk))
    messages.success(request, "Parking lot archived successfully.")
    return redirect("lots:list")


@function_required(Function.MANAGE_LOTS)
@require_POST
def lot_restore(request, pk):
    services.restore_lot(get_object_or_404(Lot, pk=pk))
    messages.success(request, "Parking lot restored successfully.")
    return redirect("lots:list")
