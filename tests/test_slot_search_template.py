
from django.template.loader import render_to_string


def test_slot_search_template_renders_form_fields():
    rendered = render_to_string(
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

    assert "Find Available Parking" in rendered
    assert 'name="lot"' in rendered
    assert 'name="vehicle"' in rendered
    assert 'name="start"' in rendered
    assert 'name="end"' in rendered
    assert "Search available slots" in rendered
