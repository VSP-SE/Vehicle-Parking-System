
"""Driver booking history view tests (FR-RES-06, TC-29)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.urls import reverse
from django.utils import timezone

from vps.accounts.models import User
from vps.billing.models import Charge, Payment
from vps.lots.models import Lot, Slot
from vps.reservations.models import Reservation


@pytest.fixture
def history_data(db):
    driver = User.objects.create_user(email="history@example.com")
    other_driver = User.objects.create_user(email="other@example.com")

    lot = Lot.objects.create(
        name="History Lot",
        address="1 Ring Road",
        opens_at="06:00",
        closes_at="23:00",
    )

    slot = Slot.objects.create(
        lot=lot,
        code="H1",
        slot_type="Standard",
        distance_rank=1,
    )

    now = timezone.now()

    def create_booking(number, owner=driver):
        return Reservation.objects.create(
            booking_ref=f"VPS-HIST-{number:04d}",
            driver=owner,
            vehicle_reg_no="KA01AB1234",
            slot=slot,
            period=DateTimeTZRange(
                now + timedelta(days=number + 1),
                now + timedelta(days=number + 1, hours=2),
            ),
            status=Reservation.Status.COMPLETED,
        )

    return {
        "driver": driver,
        "other_driver": other_driver,
        "lot": lot,
        "slot": slot,
        "create_booking": create_booking,
    }


@pytest.mark.django_db
def test_driver_sees_only_own_bookings(client, history_data):
    driver = history_data["driver"]
    own_booking = history_data["create_booking"](1)
    other_booking = history_data["create_booking"](
        2, history_data["other_driver"]
    )

    client.force_login(driver)

    response = client.get(reverse("reservations:history"))

    assert response.status_code == 200
    assert own_booking.booking_ref in response.content.decode()
    assert other_booking.booking_ref not in response.content.decode()


@pytest.mark.django_db
def test_booking_history_shows_newest_first(client, history_data):
    driver = history_data["driver"]
    older = history_data["create_booking"](1)
    newer = history_data["create_booking"](2)

    client.force_login(driver)

    response = client.get(reverse("reservations:history"))

    assert response.status_code == 200

    content = response.content.decode()
    assert content.index(newer.booking_ref) < content.index(older.booking_ref)


@pytest.mark.django_db
def test_booking_history_paginates_twenty_per_page(client, history_data):
    driver = history_data["driver"]

    for number in range(1, 22):
        history_data["create_booking"](number)

    client.force_login(driver)

    first_page = client.get(reverse("reservations:history"))
    second_page = client.get(reverse("reservations:history"), {"page": 2})

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    assert len(first_page.context["reservations"]) == 20
    assert len(second_page.context["reservations"]) == 1
    assert first_page.context["page_obj"].paginator.count == 21


@pytest.mark.django_db
def test_booking_history_displays_booking_details(client, history_data):
    driver = history_data["driver"]
    booking = history_data["create_booking"](1)

    client.force_login(driver)

    response = client.get(reverse("reservations:history"))

    content = response.content.decode()

    assert response.status_code == 200
    assert booking.booking_ref in content
    assert history_data["lot"].name in content
    assert history_data["slot"].code in content
    assert booking.vehicle_reg_no in content


@pytest.mark.django_db
def test_booking_history_displays_charges_and_payment_status(
    client, history_data
):
    driver = history_data["driver"]
    booking = history_data["create_booking"](1)

    paid_charge = Charge.objects.create(
        reservation=booking,
        kind=Charge.Kind.PARKING,
        amount_inr=Decimal("150.00"),
    )

    Charge.objects.create(
        reservation=booking,
        kind=Charge.Kind.OVERSTAY,
        amount_inr=Decimal("50.00"),
    )

    Payment.objects.create(
        charge=paid_charge,
        method=Payment.Method.UPI,
        recorded_by=driver,
    )

    client.force_login(driver)

    response = client.get(reverse("reservations:history"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "150.00" in content
    assert "50.00" in content
    assert "Paid" in content
    assert "Unpaid" in content


@pytest.mark.django_db
def test_booking_history_shows_empty_state(client, history_data):
    client.force_login(history_data["driver"])

    response = client.get(reverse("reservations:history"))

    assert response.status_code == 200
    assert "No bookings yet" in response.content.decode()


@pytest.mark.django_db
def test_anonymous_user_is_redirected_to_login(client):
    response = client.get(reverse("reservations:history"))

    assert response.status_code == 302
    assert "/accounts/login/" in response.url
