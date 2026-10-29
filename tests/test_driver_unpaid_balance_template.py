from django.template.loader import render_to_string


def test_balance_card_displays_unpaid_total():
    html = render_to_string(
        "vehicles/register.html",
        {
            "unpaid_total": 150,
            "vehicle_count": 0,
            "vehicle_limit_reached": False,
            "vehicles": [],
        },
    )

    assert "Outstanding balance" in html
    assert "₹150.00" in html
    assert "unpaid parking charges" in html


def test_balance_card_shows_zero_balance_message():
    html = render_to_string(
        "vehicles/register.html",
        {
            "unpaid_total": 0,
            "vehicle_count": 0,
            "vehicle_limit_reached": False,
            "vehicles": [],
        },
    )

    assert "₹0.00" in html
    assert "No outstanding charges" in html


def test_balance_card_handles_missing_total():
    html = render_to_string(
        "vehicles/register.html",
        {
            "vehicle_count": 0,
            "vehicle_limit_reached": False,
            "vehicles": [],
        },
    )

    assert "Your outstanding balance will appear here." in html