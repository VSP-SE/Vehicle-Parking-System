
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.utils import timezone


def make_receipt_context():
    lot = SimpleNamespace(name="Central Parking")
    slot = SimpleNamespace(code="A-012", lot=lot)

    reservation = SimpleNamespace(
        booking_ref="VPS-2026-001",
        vehicle_reg_no="KA01AB1234",
        slot=slot,
        entry_time=timezone.make_aware(datetime(2026, 10, 29, 10, 0)),
        exit_time=timezone.make_aware(datetime(2026, 10, 29, 13, 0)),
    )

    charge = SimpleNamespace(
        kind="Parking",
        amount_inr=Decimal("150.00"),
        get_kind_display=lambda: "Parking",
    )

    payment = SimpleNamespace(
        method="UPI",
        get_method_display=lambda: "UPI",
        paid_at=timezone.make_aware(datetime(2026, 10, 29, 13, 1)),
    )

    return {
        "reservation": reservation,
        "charges": [charge],
        "payment": payment,
        "payment_status": "Paid",
        "billable_duration": "3 hours",
        "hourly_rate": Decimal("50.00"),
        "total_amount": Decimal("150.00"),
    }


def test_receipt_displays_required_booking_and_payment_details():
    rendered = render_to_string(
        "billing/receipt.html",
        make_receipt_context(),
    )

    for expected in (
        "VPS-2026-001",
        "KA01AB1234",
        "Central Parking",
        "A-012",
        "Entry time",
        "Exit time",
        "3 hours",
        "₹50.00",
        "Parking",
        "₹150.00",
        "UPI",
        "Paid",
    ):
        assert expected in rendered


def test_receipt_has_browser_print_action():
    rendered = render_to_string(
        "billing/receipt.html",
        make_receipt_context(),
    )

    assert "window.print()" in rendered
    assert "Print receipt" in rendered


def test_receipt_has_itemised_charge_rows():
    rendered = render_to_string(
        "billing/receipt.html",
        make_receipt_context(),
    )

    assert "Itemised charges" in rendered
    assert "Description" in rendered
    assert "Amount" in rendered
    assert "Total" in rendered
