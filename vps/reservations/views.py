"""Presentation views for driver parking search."""

from django.shortcuts import render


def slot_search(request):
    """Render the driver slot-search page."""
    return render(
        request,
        "slots/search.html",
        {
            "lots": [],
            "vehicles": [],
            "selected_lot": "",
            "selected_vehicle": "",
            "start": "",
            "end": "",
            "slot_count": None,
            "search_error": "",
            "search_url": "",
        },
    )