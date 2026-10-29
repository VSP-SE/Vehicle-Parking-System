
from datetime import date
from decimal import Decimal

from django.template.loader import render_to_string


def test_tariff_page_renders_form_and_rate_fields():
    rendered = render_to_string(
        "lots/tariffs.html",
        {
            "lots": [],
            "tariffs": [],
            "save_tariff_url": "",
        },
    )

    assert "Tariff Management" in rendered
    assert 'name="lot_id"' in rendered
    assert 'name="slot_type"' in rendered
    assert 'name="hourly_rate_inr"' in rendered
    assert 'name="effective_from"' in rendered
    assert "Standard" in rendered
    assert "Two-wheeler" in rendered
    assert "Electric vehicle" in rendered
    assert "Accessible" in rendered


def test_tariff_page_disables_submission_without_backend_url():
    rendered = render_to_string(
        "lots/tariffs.html",
        {
            "lots": [],
            "tariffs": [],
            "save_tariff_url": "",
        },
    )

    assert 'type="submit" disabled' in rendered
    assert "backend integration" in rendered


def test_tariff_page_displays_configured_rates():
    class FakeLot:
        name = "Main Parking"

    class FakeTariff:
        lot = FakeLot()
        slot_type = "EV"
        hourly_rate_inr = Decimal("50.00")
        effective_from = date(2026, 11, 1)

        def get_slot_type_display(self):
            return "Electric vehicle"

    rendered = render_to_string(
        "lots/tariffs.html",
        {
            "lots": [],
            "tariffs": [FakeTariff()],
            "save_tariff_url": "",
        },
    )

    assert "Main Parking" in rendered
    assert "Electric vehicle" in rendered
    assert "₹50.00" in rendered
    assert "01 Nov 2026" in rendered
