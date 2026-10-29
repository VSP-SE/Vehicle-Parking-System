"""Search and booking pages: window rules (FR-SRCH-02), free-slot count (FR-SRCH-01) and
booking through to the confirmation page (FR-RES-01)."""

from datetime import time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.lots.models import Lot, Slot, SlotBlock
from vps.reservations import services
from vps.reservations.models import Reservation
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db
TOMORROW = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
    days=1
)


def at(hour, minute=0, day=TOMORROW):
    return day.replace(hour=hour, minute=minute)


def field(value):
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


@pytest.fixture
def lot():
    lot = Lot.objects.create(
        name="Lot A", address="1 Ring Road", opens_at=time(6), closes_at=time(23)
    )
    for code, rank in (("S1", 1), ("S2", 2), ("S3", 3), ("S4", 4)):
        Slot.objects.create(lot=lot, code=code, distance_rank=rank)
    return lot


@pytest.fixture
def driver():
    return User.objects.create_user(email="driver@example.com", password="s3cret-pass")


@pytest.fixture
def car(driver):
    return Vehicle.objects.create(owner=driver, registration_no="KA01AB1234", vehicle_type="Car")


def query(lot, car, start=None, end=None):
    return {
        "lot": lot.pk,
        "vehicle": car.pk,
        "start": field(start or at(11)),
        "end": field(end or at(13)),
    }


# TC-27 (FR-SRCH-02): each broken rule is named.
@pytest.mark.parametrize(
    "start,end,rule",
    [
        (lambda now: now - timedelta(minutes=10), lambda now: now + timedelta(hours=1), "past"),
        (
            lambda now: now + timedelta(days=8),
            lambda now: now + timedelta(days=8, hours=1),
            "7 days",
        ),
        (lambda now: at(10), lambda now: at(10, 20), "30 minutes"),
        (lambda now: at(10), lambda now: at(11) + timedelta(days=1), "24 hours"),
        (lambda now: at(22), lambda now: at(23, 30), "opening hours"),
        (lambda now: at(12), lambda now: at(11), "after the start"),
    ],
)
def test_search_window_rules(lot, start, end, rule):
    now = timezone.now()
    with pytest.raises(ValidationError, match=rule):
        services.validate_window(lot, start(now), end(now), now=now)


def test_search_counts_free_eligible_slots(client, driver, car, lot):
    """TC-05: blocked and overlapping-reserved slots are not counted."""
    SlotBlock.objects.create(
        slot=lot.slots.get(code="S2"), period=DateTimeTZRange(at(8), at(18)), reason="Paint"
    )
    Reservation.objects.create(
        booking_ref="VPS-000000-0001",
        vehicle_reg_no="KA02CD5678",
        slot=lot.slots.get(code="S3"),
        period=DateTimeTZRange(at(10), at(12)),
    )
    client.force_login(driver)

    response = client.get("/reservations/search/", query(lot, car))

    assert response.context["slot_count"] == 2
    assert response.context["search_error"] == ""
    assert "Book a slot" in response.content.decode()


def test_htmx_search_returns_only_the_result(client, driver, car, lot):
    client.force_login(driver)
    response = client.get("/reservations/search/", query(lot, car), HTTP_HX_REQUEST="true")
    html = response.content.decode()
    assert "4</strong>" in html
    assert "Find Available Parking" not in html


def test_search_shows_window_error(client, driver, car, lot):
    client.force_login(driver)
    response = client.get("/reservations/search/", query(lot, car, at(22), at(23, 30)))
    assert "opening hours" in response.context["search_error"]
    assert response.context["slot_count"] is None


def test_search_lists_only_open_lots_and_own_active_vehicles(client, driver, car, lot):
    Lot.objects.create(
        name="Old", address="2 Ring Road", opens_at=time(6), closes_at=time(23), is_archived=True
    )
    Vehicle.objects.create(
        owner=driver, registration_no="KA01AB9999", vehicle_type="Car", is_active=False
    )
    other = User.objects.create_user(email="other@example.com")
    Vehicle.objects.create(owner=other, registration_no="KA05XY0001", vehicle_type="Car")
    client.force_login(driver)

    response = client.get("/reservations/search/")

    assert list(response.context["lots"]) == [lot]
    assert list(response.context["vehicles"]) == [car]


def test_booking_shows_reference_and_slot(client, driver, car, lot):
    """TC-06 / FR-RES-01 end to end: the confirmation page shows the reference and slot code."""
    client.force_login(driver)

    response = client.post("/reservations/confirm/", query(lot, car), follow=True)

    reservation = Reservation.objects.get()
    html = response.content.decode()
    assert "Booking Confirmed!" in html
    assert reservation.booking_ref in html
    assert "S1" in html
    assert reservation.period == DateTimeTZRange(at(11), at(13))


def test_failed_booking_returns_to_search_with_reason(client, driver, car, lot):
    for slot in lot.slots.all():
        Reservation.objects.create(
            booking_ref=f"VPS-000000-{slot.pk:04d}",
            vehicle_reg_no="KA02CD5678",
            slot=slot,
            period=DateTimeTZRange(at(10), at(14)),
        )
    client.force_login(driver)

    response = client.post("/reservations/confirm/", query(lot, car), follow=True)

    assert response.redirect_chain[-1][0].startswith("/reservations/search/")
    assert services.NO_SLOT in response.content.decode()
    assert response.context["selected_lot"] == str(lot.pk)


def test_booking_an_invalid_window_is_refused_not_crashed(client, driver, car, lot):
    client.force_login(driver)
    response = client.post("/reservations/confirm/", query(lot, car, at(13), at(11)), follow=True)
    assert "after the start" in response.content.decode()
    assert not Reservation.objects.exists()


def test_archived_lot_cannot_be_booked(driver, car, lot):
    lot.is_archived = True
    lot.save()
    with pytest.raises(ValidationError):
        services.reserve(driver, car, lot, at(11), at(13))


def test_confirmation_is_private_to_its_driver(client, driver, car, lot):
    booking = services.reserve(driver, car, lot, at(11), at(13))
    other = User.objects.create_user(email="other@example.com")
    client.force_login(other)
    assert client.get(f"/reservations/confirmation/{booking.booking_ref}/").status_code == 404


def test_only_drivers_can_book(client, car, lot):
    attendant = User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)
    assert client.post("/reservations/confirm/", query(lot, car)).status_code == 302
    client.force_login(attendant)
    assert client.post("/reservations/confirm/", query(lot, car)).status_code == 403
    assert not Reservation.objects.exists()


@pytest.mark.parametrize(
    "role,links",
    [
        (User.Role.DRIVER, ['href="/vehicles/"', 'href="/reservations/search/"']),
        (User.Role.ADMIN, ['href="/lots/"']),
        (User.Role.ATTENDANT, ['href="/reservations/search/"']),
    ],
)
def test_header_links_to_each_roles_pages(client, role, links):
    client.force_login(User.objects.create_user(email="user@example.com", role=role))
    html = client.get("/", follow=True).content.decode()
    for link in links:
        assert link in html
