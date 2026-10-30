"""FR-BILL-04 / TC-13: the printable receipt, for attendants and the booking Driver only."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.billing.models import Payment
from vps.gate import services
from vps.lots.models import Lot, Slot, Tariff
from vps.reservations.models import Reservation

pytestmark = pytest.mark.django_db
ENTRY = timezone.make_aware(datetime(2026, 10, 27, 10))


@pytest.fixture
def attendant():
    return User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)


@pytest.fixture
def driver():
    return User.objects.create_user(email="driver@example.com")


@pytest.fixture
def completed(driver, attendant):
    """Booked 10:00-12:00, left 12:31: Rs 80 parking plus Rs 30 overstay."""
    lot = Lot.objects.create(
        name="Lot A", address="Ring Road", opens_at=time(6), closes_at=time(23)
    )
    slot = Slot.objects.create(lot=lot, code="A-01", distance_rank=1)
    Tariff.objects.create(
        lot=lot, slot_type="Standard", hourly_rate_inr="40.00", effective_from=ENTRY.date()
    )
    booking = Reservation.objects.create(
        booking_ref="VPS-261027-0001",
        driver=driver,
        vehicle_reg_no="KA01AB1234",
        slot=slot,
        period=DateTimeTZRange(ENTRY, ENTRY + timedelta(hours=2)),
        status=Reservation.Status.ACTIVE,
        entry_time=ENTRY,
    )
    services.checkout_vehicle(booking.booking_ref, attendant, now=ENTRY + timedelta(minutes=151))
    return booking


URL = "/gate/receipt/VPS-261027-0001/print/"


def test_tc13_printable_receipt_shows_every_required_item(client, attendant, completed):
    client.force_login(attendant)
    html = client.get(URL).content.decode()

    for text in (
        "VPS-261027-0001",
        "KA01AB1234",
        "A-01",
        "Lot A",
        "2.5 hours",
        "₹40.00",
        "₹80.00",
        "₹30.00",
        "₹110.00",
        "Unpaid",
        "window.print()",
    ):
        assert text in html, text


def test_payment_status_and_method_follow_payments(client, attendant, completed):
    parking, overstay = completed.charges.order_by("id")
    Payment.objects.create(charge=parking, method=Payment.Method.UPI, recorded_by=attendant)
    client.force_login(attendant)

    partial = client.get(URL)
    Payment.objects.create(charge=overstay, method=Payment.Method.CASH, recorded_by=attendant)
    paid = client.get(URL)

    assert partial.context["payment_status"] == "Partially paid"
    assert partial.context["balance_due"] == Decimal("30.00")
    assert paid.context["payment_status"] == "Paid"
    assert paid.context["payment"].method == Payment.Method.CASH


def test_the_booking_driver_can_print_their_receipt(client, driver, completed):
    client.force_login(driver)
    assert client.get(URL).status_code == 200


def test_other_drivers_and_admins_cannot_see_it(client, completed):
    client.force_login(User.objects.create_user(email="other@example.com"))
    assert client.get(URL).status_code == 404
    client.force_login(User.objects.create_user(email="admin@example.com", role=User.Role.ADMIN))
    assert client.get(URL).status_code == 403


def test_guests_are_sent_to_sign_in(client, completed):
    assert client.get(URL).status_code == 302


def test_unfinished_stays_have_no_receipt(client, attendant, completed):
    Reservation.objects.filter(pk=completed.pk).update(status=Reservation.Status.ACTIVE)
    client.force_login(attendant)
    assert client.get(URL).status_code == 404


def test_gate_receipt_links_to_the_printable_one(client, attendant, completed):
    client.force_login(attendant)
    html = client.get("/gate/receipt/VPS-261027-0001/").content.decode()
    assert f'href="{URL}"' in html
