# tests/test_slot_search.py

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from vps.allocation.search import (
    SearchWindowError,
    validate_search_window,
)


@pytest.fixture
def lot():
    # Assumes the lot's opening hours are stored as time fields.
    return SimpleNamespace(
        opening_time=timezone.datetime.strptime("06:00", "%H:%M").time(),
        closing_time=timezone.datetime.strptime("23:00", "%H:%M").time(),
    )


@pytest.mark.parametrize(
    ("start_offset", "duration", "expected_message"),
    [
        (
            timedelta(minutes=-30),
            timedelta(hours=1),
            "past",
        ),
        (
            timedelta(days=8),
            timedelta(hours=1),
            "7 days",
        ),
        (
            timedelta(hours=1),
            timedelta(minutes=15),
            "30 minutes",
        ),
        (
            timedelta(hours=1),
            timedelta(hours=25),
            "24 hours",
        ),
    ],
)
def test_rejects_invalid_search_windows(
    lot,
    start_offset,
    duration,
    expected_message,
):
    now = timezone.now()
    start = now + start_offset
    end = start + duration

    with pytest.raises(SearchWindowError, match=expected_message):
        validate_search_window(
            lot=lot,
            start=start,
            end=end,
            now=now,
        )


@pytest.mark.django_db
def test_rejects_window_outside_opening_hours(lot):
    now = timezone.now()
    local_now = timezone.localtime(now)

    # Construct a future same-day window outside the configured hours.
    future_date = local_now.date() + timedelta(days=1)
    start = timezone.make_aware(
        timezone.datetime.combine(
            future_date,
            timezone.datetime.strptime("05:00", "%H:%M").time(),
        ),
        timezone.get_current_timezone(),
    )
    end = start + timedelta(hours=1)

    with pytest.raises(SearchWindowError, match="opening hours"):
        validate_search_window(
            lot=lot,
            start=start,
            end=end,
            now=now,
        )