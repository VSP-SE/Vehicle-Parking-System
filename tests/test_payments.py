"""FR-GATE-05 payment recording and TC-30 unpaid-charge booking recovery."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.billing import services
from vps.billing.models import Charge, Payment
from vps.lots.models import Lot, Slot
from vps.reservations.models import Reservation
from vps.reservations.services import UNPAID_CHARGE, reserve
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db
TOMORROW = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
    days=1
)
ALREADY_PAID = "This charge has already been paid."


@pytest.fixture
def attendant():
    return User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)


@pytest.fixture
def charge():
    driver = User.objects.create_user(email="driver@example.com")
    Vehicle.objects.create(owner=driver, registration_no="KA01AB1234", vehicle_type="Car")
    lot = Lot.objects.create(
        name="Lot A", address="Ring Road", opens_at=time(6), closes_at=time(23)
    )
    slot = Slot.objects.create(lot=lot, code="S1", distance_rank=1)
    reservation = Reservation.objects.create(
        booking_ref="VPS-261026-0001",
        driver=driver,
        vehicle_reg_no="KA01AB1234",
        slot=slot,
        period=DateTimeTZRange(TOMORROW.replace(hour=8), TOMORROW.replace(hour=9)),
        status=Reservation.Status.CANCELLED,
    )
    return Charge.objects.create(
        reservation=reservation, kind=Charge.Kind.NO_SHOW, amount_inr=Decimal("50.00")
    )


def test_tc30_payment_unblocks_next_reservation(client, attendant, charge):
    """TC-30: paying a cancelled booking's no-show charge restores booking eligibility."""
    booking = charge.reservation
    driver = booking.driver
    car = driver.vehicles.get()
    start, end = TOMORROW.replace(hour=11), TOMORROW.replace(hour=12)
    with pytest.raises(ValidationError) as error:
        reserve(driver, car, booking.slot.lot, start, end)
    assert error.value.message_dict == {"__all__": [UNPAID_CHARGE]}

    client.force_login(attendant)
    response = client.post(
        f"/gate/payments/{charge.pk}/", {"method": "UPI", "q": booking.booking_ref}, follow=True
    )

    assert response.status_code == 200
    payment = Payment.objects.get(charge=charge)
    assert payment.method == "UPI"
    assert payment.recorded_by == attendant
    assert payment.paid_at is not None
    audit = AuditLog.objects.get(action="payment.recorded")
    assert audit.actor == attendant
    assert audit.target == f"charge:{charge.pk}"
    assert audit.before is None
    assert audit.after == {
        "reservation": "VPS-261026-0001",
        "kind": "NoShow",
        "amount_inr": "50.00",
        "method": "UPI",
    }
    assert reserve(driver, car, booking.slot.lot, start, end).status == "Reserved"


@pytest.mark.parametrize("method", ["Cash", "UPI", "Card"])
def test_each_payment_method_is_accepted(attendant, charge, method):
    payment = services.record_payment(attendant, charge, method)
    assert Payment.objects.get(pk=payment.pk).method == method
    assert AuditLog.objects.get().after["method"] == method


@pytest.mark.parametrize("method", ["Bitcoin", "", "cash", None])
def test_invalid_method_creates_nothing(attendant, charge, method):
    with pytest.raises(ValidationError):
        services.record_payment(attendant, charge, method)
    assert not Payment.objects.exists()
    assert not AuditLog.objects.exists()


def test_already_paid_charge_is_refused(attendant, charge):
    services.record_payment(attendant, charge, "Cash")
    with pytest.raises(ValidationError, match=ALREADY_PAID):
        services.record_payment(attendant, charge, "UPI")
    assert Payment.objects.count() == AuditLog.objects.count() == 1


@pytest.mark.parametrize("role", [User.Role.DRIVER, User.Role.ADMIN, None])
def test_service_refuses_non_attendants(charge, role):
    user = (
        User.objects.create_user(email="other@example.com", role=role) if role else AnonymousUser()
    )
    with pytest.raises(ValidationError):
        services.record_payment(user, charge, "Cash")
    assert not Payment.objects.exists()
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("role", [User.Role.DRIVER, User.Role.ADMIN])
def test_payment_views_forbid_other_roles(client, charge, role):
    client.force_login(User.objects.create_user(email="other@example.com", role=role))
    assert client.get("/gate/payments/").status_code == 403
    assert client.post(f"/gate/payments/{charge.pk}/", {"method": "Cash"}).status_code == 403
    assert not Payment.objects.exists()


def test_payment_views_redirect_guests_to_login(client, charge):
    for response in (
        client.get("/gate/payments/"),
        client.post(f"/gate/payments/{charge.pk}/", {"method": "Cash"}),
    ):
        assert response.status_code == 302
        assert urlparse(response.url).path == "/accounts/login/"
        assert "next" in parse_qs(urlparse(response.url).query)


@pytest.mark.parametrize("query", ["vps-261026-0001", "VPS-261026-0001", " ka 01 ab 1234 "])
def test_search_finds_only_unpaid_charges_oldest_first(charge, attendant, query):
    second = Charge.objects.create(reservation=charge.reservation, kind="Parking", amount_inr=100)
    paid = Charge.objects.create(reservation=charge.reservation, kind="Overstay", amount_inr=20)
    Payment.objects.create(charge=paid, recorded_by=attendant, method="Card")
    unrelated = Reservation.objects.create(
        booking_ref="VPS-261026-0002",
        vehicle_reg_no="KA02CD5678",
        slot=charge.reservation.slot,
        period=charge.reservation.period,
        status="Cancelled",
    )
    Charge.objects.create(reservation=unrelated, kind="Parking", amount_inr=10)
    results = list(services.unpaid_charges(query))
    assert results == [charge, second]
    with connection.execute_wrapper(_forbid_queries):
        assert results[0].reservation.booking_ref == "VPS-261026-0001"


def _forbid_queries(execute, sql, params, many, context):
    pytest.fail("Search results must preload their reservations")


@pytest.mark.parametrize("query", ["", "   ", "missing"])
def test_search_returns_nothing_for_blank_or_unknown_query(charge, query):
    assert list(services.unpaid_charges(query)) == []


def test_payment_page_renders_search_and_form(client, attendant, charge):
    client.force_login(attendant)
    response = client.get("/gate/payments/", {"q": "ka 01 ab 1234"})
    html = response.content.decode()
    assert response.status_code == 200
    assert list(response.context["charges"]) == [charge]
    for text in (
        "VPS-261026-0001",
        "KA01AB1234",
        "No-show",
        "Rs 50.00",
        'name="method"',
        'name="csrfmiddlewaretoken"',
        'name="q"',
        f'action="/gate/payments/{charge.pk}/"',
        "Cash",
        "UPI",
        "Card",
        "Record payment",
        'href="/gate/payments/"',
    ):
        assert text in html
    assert list(client.get("/gate/payments/").context["charges"]) == []


@pytest.mark.parametrize(
    "method,expected",
    [
        ("UPI", "Payment of Rs 50.00 recorded for VPS-261026-0001"),
        ("invalid", "Choose Cash, UPI or Card."),
    ],
)
def test_payment_redirect_preserves_query_and_displays_message(
    client, attendant, charge, method, expected
):
    client.force_login(attendant)
    response = client.post(
        f"/gate/payments/{charge.pk}/", {"method": method, "q": " ka 01 ab 1234 "}, follow=True
    )
    assert response.status_code == 200
    assert parse_qs(urlparse(response.redirect_chain[0][0]).query) == {"q": [" ka 01 ab 1234 "]}
    assert expected in response.content.decode()


def test_duplicate_payment_message_after_redirect(client, attendant, charge):
    services.record_payment(attendant, charge, "Cash")
    client.force_login(attendant)
    response = client.post(
        f"/gate/payments/{charge.pk}/", {"method": "Card", "q": "KA01AB1234"}, follow=True
    )
    assert ALREADY_PAID in response.content.decode()
    assert Payment.objects.count() == AuditLog.objects.count() == 1


def test_unknown_charge_and_post_only(client, attendant):
    client.force_login(attendant)
    assert client.post("/gate/payments/999999/", {"method": "UPI"}).status_code == 404
    assert client.get("/gate/payments/999999/").status_code == 405


def test_audit_failure_rolls_back_payment(attendant, charge, monkeypatch):
    def fail_audit(**kwargs):
        raise IntegrityError("Audit insert failed")

    monkeypatch.setattr(AuditLog.objects, "create", fail_audit)
    with pytest.raises(IntegrityError, match="Audit insert failed"):
        services.record_payment(attendant, charge, "UPI")
    assert not Payment.objects.exists()
    assert not AuditLog.objects.exists()


def _pay_in_thread(barrier, attendant, charge):
    try:
        barrier.wait(timeout=10)
        services.record_payment(attendant, charge, "UPI")
        return "paid"
    except ValidationError as error:
        return error.messages[0]
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
def test_concurrent_payments_have_one_winner(attendant, charge):
    """FR-GATE-05: concurrent attendants record one payment and one audit entry."""
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _pay_in_thread(barrier, attendant, charge), range(2)))
    assert sorted(results) == sorted(["paid", ALREADY_PAID])
    assert Payment.objects.count() == AuditLog.objects.count() == 1


def test_unique_constraint_race_is_reported_as_already_paid(attendant, charge, monkeypatch):
    """FR-GATE-05: the database duplicate safeguard returns the same payment error."""
    from django.db.models import QuerySet

    Payment.objects.create(charge=charge, recorded_by=attendant, method="Cash")
    original_exists = QuerySet.exists

    def stale_payment_check(queryset):
        return False if queryset.model is Payment else original_exists(queryset)

    monkeypatch.setattr(QuerySet, "exists", stale_payment_check)
    with pytest.raises(ValidationError, match=ALREADY_PAID):
        services.record_payment(attendant, charge, "UPI")
    assert Payment.objects.count() == 1
    assert not AuditLog.objects.exists()
