# vps/allocation/search.py

from datetime import  timedelta

from django.utils import timezone

from vps.allocation.services import is_slot_eligible
from vps.lots.models import Slot
from vps.reservations.models import Reservation


MIN_WINDOW = timedelta(minutes=30)
MAX_WINDOW = timedelta(hours=24)
MAX_START_AHEAD = timedelta(days=7)


class SearchWindowError(ValueError):
    """Raised when a requested parking search window is invalid."""


def validate_search_window(*, lot, start, end, now=None):
    """Validate time ordering, search horizon, duration and lot opening hours."""
    now = now or timezone.now()

    if timezone.is_naive(start) or timezone.is_naive(end):
        raise SearchWindowError(
            "Enter a valid start and end date/time with a timezone."
        )

    if start < now:
        raise SearchWindowError("The start time cannot be in the past.")

    if start > now + MAX_START_AHEAD:
        raise SearchWindowError(
            "The start time cannot be more than 7 days ahead."
        )

    if end <= start:
        raise SearchWindowError("The end time must be after the start time.")

    duration = end - start

    if duration < MIN_WINDOW:
        raise SearchWindowError(
            "The parking window must be at least 30 minutes."
        )

    if duration > MAX_WINDOW:
        raise SearchWindowError(
            "The parking window cannot exceed 24 hours."
        )

    # Assumes the lot's opening_time and closing_time are time fields.
    # This implementation supports a same-day opening interval only.
    local_start = timezone.localtime(start)
    local_end = timezone.localtime(end)

    if local_start.date() != local_end.date():
        raise SearchWindowError(
            "The selected window must fall within the lot's opening hours."
        )

    if (
        local_start.time().replace(tzinfo=None) < lot.opening_time
        or local_end.time().replace(tzinfo=None) > lot.closing_time
    ):
        raise SearchWindowError(
            "The selected window falls outside the lot's opening hours."
        )


def count_available_slots(*, lot, vehicle, start, end):
    """Count eligible slots free for the entire requested time window."""

    slots = Slot.objects.filter(
        lot=lot,
        is_active=True,
    )

    available_count = 0

    for slot in slots:
        if not is_slot_eligible(slot, vehicle):
            continue

        # Half-open interval overlap:
        # existing_start < requested_end AND existing_end > requested_start
        has_reservation = Reservation.objects.filter(
            slot=slot,
            start_time__lt=end,
            end_time__gt=start,
            status__in=["Reserved", "CheckedIn"],
        ).exists()

        if has_reservation:
            continue

        # TODO: Exclude slots with maintenance blocks overlapping this window.
        # Use the actual block model and its start/end field names.

        available_count += 1

    return available_count


def search_available_slots(*, lot, vehicle, start, end, now=None):
    """Validate a search request and return the available slot count."""
    validate_search_window(
        lot=lot,
        start=start,
        end=end,
        now=now,
    )

    return count_available_slots(
        lot=lot,
        vehicle=vehicle,
        start=start,
        end=end,
    )