"""Outstanding balance card on the Driver's home page (FR-BILL-05, TC-30)."""

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.template.loader import render_to_string
from django.utils import timezone

from vps.accounts.models import User
from vps.billing.models import Charge, Payment
from vps.lots.models import Lot, Slot
from vps.reservations.models import Reservation


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


@pytest.mark.django_db
def test_tc30_home_page_shows_only_unpaid_charges(client):
    """TC-30 (FR-BILL-05): the Driver's home page totals their unpaid charges only."""
    lot = Lot.objects.create(
        name="Lot A", address="1 Ring Road", opens_at=time(6), closes_at=time(23)
    )
    slot = Slot.objects.create(lot=lot, code="S1", slot_type="Standard", distance_rank=1)
    driver = User.objects.create_user(email="d@example.com")
    other = User.objects.create_user(email="o@example.com")
    start = timezone.now() - timedelta(days=1)

    def charge(owner, n, amount):
        booking = Reservation.objects.create(
            booking_ref=f"VPS-261029-{n:04d}",
            driver=owner,
            vehicle_reg_no="KA01AB0001",
            slot=slot,
            period=DateTimeTZRange(
                start + timedelta(hours=2 * n), start + timedelta(hours=2 * n + 1)
            ),
            status=Reservation.Status.COMPLETED,
        )
        return Charge.objects.create(
            reservation=booking, kind=Charge.Kind.NO_SHOW, amount_inr=amount
        )

    charge(driver, 1, Decimal("50.00"))
    charge(driver, 2, Decimal("120.50"))
    paid = charge(driver, 3, Decimal("30.00"))
    Payment.objects.create(charge=paid, method=Payment.Method.UPI, recorded_by=driver)
    charge(other, 4, Decimal("999.00"))
    client.force_login(driver)

    response = client.get(client.get("/").url)

    assert response.context["unpaid_total"] == Decimal("170.50")
    assert "₹170.50" in response.content.decode()


@pytest.mark.django_db
def test_tc30_driver_with_nothing_owed_sees_zero(client):
    client.force_login(User.objects.create_user(email="d@example.com"))
    response = client.get("/vehicles/")
    assert response.context["unpaid_total"] == 0
    assert "No outstanding charges" in response.content.decode()
