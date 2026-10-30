
"""Tests for the Gate Attendant dashboard (#47)."""

from datetime import time, timedelta

import pytest
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.urls import reverse
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.lots.models import Lot, Slot, Tariff
from vps.reservations.models import Reservation

pytestmark = pytest.mark.django_db


@pytest.fixture
def attendant():
    return User.objects.create_user(
        email="dashboard-gate@example.com",
        role=User.Role.ATTENDANT,
    )


@pytest.fixture
def lot():
    return Lot.objects.create(
        name="Dashboard Lot",
        address="Ring Road",
        opens_at=time(6),
        closes_at=time(23),
    )


@pytest.fixture
def slot(lot):
    return Slot.objects.create(
        lot=lot,
        code="D-01",
        distance_rank=1,
    )


@pytest.fixture
def tariff(lot):
    return Tariff.objects.create(
        lot=lot,
        slot_type="Standard",
        hourly_rate_inr="40.00",
        effective_from=timezone.localdate(),
    )


@pytest.fixture
def reserved_booking(slot):
    now = timezone.now()
    return Reservation.objects.create(
        booking_ref="VPS-261030-0047",
        vehicle_reg_no="KA01AB4747",
        slot=slot,
        period=DateTimeTZRange(
            now - timedelta(minutes=5),
            now + timedelta(hours=2),
        ),
        status=Reservation.Status.RESERVED,
    )


@pytest.fixture
def active_booking(slot, tariff):
    now = timezone.now()
    entry = now - timedelta(hours=1)
    return Reservation.objects.create(
        booking_ref="VPS-261030-0048",
        vehicle_reg_no="KA02CD4848",
        slot=slot,
        period=DateTimeTZRange(
            entry,
            now + timedelta(hours=7),
        ),
        status=Reservation.Status.ACTIVE,
        entry_time=entry,
    )


def test_dashboard_loads_for_attendant(client, attendant, lot):
    client.force_login(attendant)

    response = client.get(reverse("gate:dashboard"))

    assert response.status_code == 200
    assert b"Gate Operations" in response.content
    assert b"Dashboard Lot" in response.content
    assert response.context["checkin_url"] == reverse("gate:checkin")
    assert response.context["checkout_url"] == reverse("gate:dashboard_checkout")
    assert response.context["walkin_url"] == reverse("gate:dashboard_walk_in")


def test_dashboard_redirects_anonymous_user(client):
    response = client.get(reverse("gate:dashboard"))

    assert response.status_code == 302
    assert "login" in response.url


@pytest.mark.parametrize(
    "role",
    [User.Role.DRIVER, User.Role.ADMIN],
)
@pytest.mark.parametrize(
    "url_name,method",
    [
        ("gate:dashboard", "get"),
        ("gate:checkin", "post"),
        ("gate:dashboard_checkout", "post"),
        ("gate:dashboard_walk_in", "post"),
    ],
)
def test_dashboard_forbids_other_roles(client, role, url_name, method):
    user = User.objects.create_user(
        email=f"{role.lower()}-dashboard@example.com",
        role=role,
    )
    client.force_login(user)

    url = reverse(url_name)
    response = getattr(client, method)(url)

    assert response.status_code == 403


def test_dashboard_checkin_activates_reserved_booking(
    client,
    attendant,
    reserved_booking,
):
    client.force_login(attendant)

    response = client.post(
        reverse("gate:checkin"),
        {"reference": reserved_booking.booking_ref},
    )

    reserved_booking.refresh_from_db()

    assert response.status_code == 200
    assert reserved_booking.status == Reservation.Status.ACTIVE
    assert reserved_booking.entry_time is not None
    assert b"Checked in" in response.content

    audit = AuditLog.objects.get(
        target=f"reservation:{reserved_booking.booking_ref}",
    )
    assert audit.action == "reservation.checked_in"
    assert audit.actor == attendant


def test_dashboard_checkin_rejects_expired_booking(
    client,
    attendant,
    slot,
):
    now = timezone.now()
    booking = Reservation.objects.create(
        booking_ref="VPS-261030-0049",
        vehicle_reg_no="KA03EF4949",
        slot=slot,
        period=DateTimeTZRange(
            now - timedelta(minutes=30),
            now + timedelta(hours=2),
        ),
        status=Reservation.Status.RESERVED,
    )
    client.force_login(attendant)

    response = client.post(
        reverse("gate:checkin"),
        {"reference": booking.booking_ref},
    )

    booking.refresh_from_db()

    assert response.status_code == 200
    assert booking.status == Reservation.Status.RESERVED
    assert booking.entry_time is None
    assert b"grace period has expired" in response.content


def test_dashboard_checkout_redirects_to_receipt(
    client,
    attendant,
    active_booking,
):
    client.force_login(attendant)

    response = client.post(
        reverse("gate:dashboard_checkout"),
        {"reference": active_booking.booking_ref},
    )

    active_booking.refresh_from_db()

    assert response.status_code == 302
    assert response.url == reverse(
        "gate:receipt",
        kwargs={"booking_ref": active_booking.booking_ref},
    )
    assert active_booking.status == Reservation.Status.COMPLETED



def test_dashboard_walk_in_registers_vehicle(
    client,
    attendant,
    lot,
    slot,
):
    client.force_login(attendant)

    response = client.post(
        reverse("gate:dashboard_walk_in"),
        {
            "lot": lot.pk,
            "registration_no": "KA05MN4747",
            "vehicle_type": "Car",
        },
    )

    booking = Reservation.objects.get(vehicle_reg_no="KA05MN4747")

    assert response.status_code == 200
    assert booking.status == Reservation.Status.ACTIVE
    assert booking.is_walk_in is True
    assert booking.driver is None
    assert booking.slot == slot
    assert b"Walk-in KA05MN4747 parked" in response.content



def test_dashboard_walk_in_rejects_invalid_lot(
    client,
    attendant,
):
    client.force_login(attendant)

    response = client.post(
        reverse("gate:dashboard_walk_in"),
        {
            "lot": 999999,
            "registration_no": "KA05MN4748",
            "vehicle_type": "Car",
        },
    )

    assert response.status_code == 200
    assert b"Select a valid choice" in response.content
    assert not Reservation.objects.filter(
        vehicle_reg_no="KA05MN4748",
    ).exists()
