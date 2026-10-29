
from django.template.loader import render_to_string
from django.test import override_settings


@override_settings(ROOT_URLCONF="vps.urls")
def test_confirmation_page_shows_booking_reference_and_slot():
    rendered = render_to_string(
        "reservations/confirmation.html",
        {
            "booking_reference": "VPS-261021-0001",
            "slot_code": "A-12",
            "lot_name": "Main Campus",
        },
    )

    assert "Booking Confirmed!" in rendered
    assert "VPS-261021-0001" in rendered
    assert "A-12" in rendered
    assert "Main Campus" in rendered


@override_settings(ROOT_URLCONF="vps.urls")
def test_confirmation_page_does_not_fake_a_booking():
    rendered = render_to_string(
        "reservations/confirmation.html",
        {
            "booking_reference": "",
            "slot_code": "",
            "booking_error": "",
            "confirm_url": "",
        },
    )

    assert "Confirm Your Booking" in rendered
    assert "Booking confirmation will be available" in rendered
    assert "VPS-261021-0001" not in rendered

