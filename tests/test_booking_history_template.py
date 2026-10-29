from datetime import datetime
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.utils import timezone


def make_reservation():
    lot = SimpleNamespace(name="Central Parking")
    slot = SimpleNamespace(code="A-012", lot=lot)

    period = SimpleNamespace(
        lower=timezone.make_aware(datetime(2026, 10, 29, 10, 0)),
        upper=timezone.make_aware(datetime(2026, 10, 29, 13, 0)),
    )

    charge = SimpleNamespace(
        kind="Parking",
        amount_inr=150,
        get_kind_display=lambda: "Parking",
    )

    return SimpleNamespace(
        booking_ref="VPS-2026-014",
        slot=slot,
        period=period,
        status="Reserved",
        get_status_display=lambda: "Reserved",
        charges=SimpleNamespace(all=lambda: [charge]),
    )


def test_booking_history_displays_required_reservation_fields():
    rendered = render_to_string(
        "reservations/history.html",
        {
            "reservations": [make_reservation()],
            "page_obj": None,
        },
    )

    for expected in (
        "My Bookings",
        "VPS-2026-014",
        "Central Parking",
        "A-012",
        "29 Oct 2026",
        "Reserved",
        "Parking",
        "₹150.00",
    ):
        assert expected in rendered


def test_booking_history_shows_empty_state():
    rendered = render_to_string(
        "reservations/history.html",
        {
            "reservations": [],
            "page_obj": None,
        },
    )

    assert "No bookings yet" in rendered
    assert "Find parking" in rendered


def test_booking_history_has_pagination_navigation_when_multiple_pages():
    page_obj = SimpleNamespace(
        paginator=SimpleNamespace(count=21, num_pages=2),
        number=1,
        has_previous=False,
        has_next=True,
        next_page_number=2,
    )

    rendered = render_to_string(
        "reservations/history.html",
        {
            "reservations": [make_reservation()],
            "page_obj": page_obj,
        },
    )

    assert 'aria-label="Booking history pages"' in rendered
    assert "Page 1 of 2" in rendered
    assert "?page=2" in rendered
    assert "Next" in rendered
