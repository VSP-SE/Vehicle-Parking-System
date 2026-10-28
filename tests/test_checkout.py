"""FR-GATE-04 / FR-BILL-01–04: atomic checkout and itemised receipts."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.urls import reverse
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.billing.models import Charge, Payment
from vps.gate import services
from vps.lots.models import Lot, Slot, Tariff
from vps.reservations.models import Reservation

pytestmark = pytest.mark.django_db


@pytest.fixture
def attendant():
    return User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)


@pytest.fixture
def entry():
    return timezone.make_aware(datetime(2026, 10, 27, 10))


@pytest.fixture
def booking(entry):
    lot = Lot.objects.create(
        name="Lot A", address="Ring Road", opens_at=time(6), closes_at=time(23)
    )
    slot = Slot.objects.create(lot=lot, code="A-01", distance_rank=1)
    Tariff.objects.create(
        lot=lot, slot_type="Standard", hourly_rate_inr="40.00", effective_from=entry.date()
    )
    return Reservation.objects.create(
        booking_ref="VPS-261027-0001",
        vehicle_reg_no="KA01AB1234",
        slot=slot,
        period=DateTimeTZRange(entry, entry + timedelta(hours=8)),
        status=Reservation.Status.ACTIVE,
        entry_time=entry,
    )


def checkout(booking, attendant, now):
    return services.checkout_vehicle(booking.booking_ref, attendant, now=now)


@pytest.mark.parametrize("minutes,amount", [(20, "40.00"), (61, "60.00"), (130, "100.00")])
def test_tc13_rounded_parking_charge(booking, attendant, entry, minutes, amount):
    result = checkout(booking, attendant, entry + timedelta(minutes=minutes))
    booking.refresh_from_db()
    assert result.pk == booking.pk
    assert booking.status == "Completed"
    assert booking.exit_time == entry + timedelta(minutes=minutes)
    charge = booking.charges.get()
    assert charge.kind == "Parking"
    assert charge.amount_inr == Decimal(amount)


@pytest.mark.parametrize(
    "minutes,overstay", [(128, None), (130, None), (131, "30.00"), (160, "30.00"), (161, "60.00")]
)
def test_tc14_grace_and_overstay_rounding(booking, attendant, entry, minutes, overstay):
    booking.period = DateTimeTZRange(entry, entry + timedelta(hours=2))
    booking.save()
    checkout(booking, attendant, entry + timedelta(minutes=minutes))
    assert booking.charges.get(kind="Parking").amount_inr == Decimal("80.00")
    if overstay is None:
        assert not booking.charges.filter(kind="Overstay").exists()
    else:
        assert booking.charges.get(kind="Overstay").amount_inr == Decimal(overstay)


@pytest.mark.parametrize("enter_today,amount", [(False, "80.00"), (True, "100.00")])
def test_tc33_uses_tariff_at_entry(booking, attendant, entry, enter_today, amount):
    today = entry + timedelta(days=1)
    Tariff.objects.create(
        lot=booking.slot.lot,
        slot_type="Standard",
        hourly_rate_inr="50.00",
        effective_from=today.date(),
    )
    booking.entry_time = today if enter_today else today.replace(hour=23) - timedelta(days=1)
    booking.period = DateTimeTZRange(booking.entry_time, today + timedelta(days=1))
    booking.save()
    checkout(booking, attendant, booking.entry_time + timedelta(hours=2))
    assert booking.charges.get().amount_inr == Decimal(amount)


def test_tariff_uses_local_entry_date(booking, attendant):
    with timezone.override("Asia/Kolkata"):
        booking.entry_time = timezone.make_aware(datetime(2026, 10, 27, 0, 15))
        booking.save()
        checkout(booking, attendant, booking.entry_time + timedelta(hours=2))
    assert booking.charges.get().amount_inr == Decimal("80.00")


def test_walk_in_bills_until_exit_without_overstay(booking, attendant, entry):
    booking.is_walk_in = True
    booking.period = DateTimeTZRange(entry, entry + timedelta(hours=1))
    booking.save()
    checkout(booking, attendant, entry + timedelta(minutes=130))
    assert booking.charges.get().amount_inr == Decimal("100.00")


def test_checkout_frees_slot_and_audits(booking, attendant, entry):
    exit_time = entry + timedelta(hours=2)
    checkout(booking, attendant, exit_time)
    replacement = Reservation.objects.create(
        booking_ref="VPS-261027-0002",
        vehicle_reg_no="KA02CD5678",
        slot=booking.slot,
        period=DateTimeTZRange(exit_time, exit_time + timedelta(hours=1)),
    )
    assert replacement.status == "Reserved"
    audit = AuditLog.objects.get()
    assert audit.actor == attendant
    assert audit.action == "reservation.checked_out"
    assert audit.target == f"reservation:{booking.booking_ref}"
    assert audit.before == {"status": "Active"}
    assert audit.after["status"] == "Completed"
    assert audit.after["vehicle_reg_no"] == booking.vehicle_reg_no
    assert audit.after["slot"] == booking.slot.code
    assert audit.after["exit_time"] == exit_time.isoformat()
    assert audit.after["parking_amount_inr"] == "80.00"
    assert Decimal(audit.after["overstay_hours"]) == 0
    assert audit.after["overstay_amount_inr"] == "0.00"


@pytest.mark.parametrize("query", [" vps-261027-0001 ", " ka 01 ab 1234 "])
def test_lookup_normalises_reference_and_registration(booking, attendant, entry, query):
    assert services.checkout_vehicle(query, attendant, now=entry).pk == booking.pk


@pytest.mark.parametrize(
    "problem,message",
    [
        ("completed", "No Active reservation"),
        ("missing", "No Active reservation"),
        ("blank", "Enter a booking reference"),
        ("no_entry", "no recorded entry time"),
        ("no_tariff", "No applicable tariff"),
        ("future_tariff", "No applicable tariff"),
        ("early_exit", "earlier than entry"),
        ("invalid_end", "reserved end"),
        ("missing_end", "reserved end"),
        ("charged", "already been recorded"),
    ],
)
def test_invalid_checkout_has_non_field_error_and_no_writes(
    booking, attendant, entry, problem, message
):
    query = booking.booking_ref
    if problem == "completed":
        booking.status = "Completed"
    elif problem == "missing":
        query = "missing"
    elif problem == "blank":
        query = "  "
    elif problem == "no_entry":
        booking.entry_time = None
    elif problem == "no_tariff":
        Tariff.objects.all().delete()
    elif problem == "future_tariff":
        Tariff.objects.update(effective_from=entry.date() + timedelta(days=1))
    elif problem == "invalid_end":
        booking.period = DateTimeTZRange(entry - timedelta(hours=2), entry - timedelta(hours=1))
    elif problem == "missing_end":
        booking.period = DateTimeTZRange(entry, None)
    elif problem == "charged":
        Charge.objects.create(reservation=booking, kind="Parking", amount_inr="40.00")
    booking.save()
    before_count = Charge.objects.count()
    exit_time = entry - timedelta(seconds=1) if problem == "early_exit" else entry
    with pytest.raises(ValidationError, match=message) as error:
        services.checkout_vehicle(query, attendant, now=exit_time)
    assert list(error.value.message_dict) == ["__all__"]
    booking.refresh_from_db()
    assert booking.status == ("Completed" if problem == "completed" else "Active")
    assert booking.exit_time is None
    assert Charge.objects.count() == before_count
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("role", ["Driver", "Admin", None])
def test_service_refuses_non_attendants(booking, entry, role):
    user = (
        User.objects.create_user(email="other@example.com", role=role) if role else AnonymousUser()
    )
    with pytest.raises(ValidationError):
        checkout(booking, user, entry)
    assert not Charge.objects.exists()
    assert not AuditLog.objects.exists()


def test_checkout_page_redirect_and_complete_receipt(
    client, booking, attendant, entry, monkeypatch
):
    exit_time = entry + timedelta(minutes=160)
    booking.period = DateTimeTZRange(entry, entry + timedelta(hours=2))
    booking.save()
    monkeypatch.setattr(services.timezone, "now", lambda: exit_time)
    client.force_login(attendant)
    page = client.get(reverse("gate:checkout"))
    assert page.status_code == 200
    assert 'name="query"' in page.content.decode()
    assert 'name="csrfmiddlewaretoken"' in page.content.decode()
    assert 'href="/gate/checkout/">Check-out</a>' in page.content.decode()
    response = client.post(reverse("gate:checkout"), {"query": booking.booking_ref}, follow=True)
    assert response.redirect_chain == [(reverse("gate:receipt", args=[booking.booking_ref]), 302)]
    assert response.status_code == 200
    html = response.content.decode()
    for text in (
        booking.booking_ref,
        "KA01AB1234",
        "Lot A",
        "A-01",
        "Entry time",
        "Exit time",
        "27 Oct 2026, 10:00",
        "27 Oct 2026, 12:40",
        "Billable duration",
        "2.0 hours",
        "Hourly rate",
        "₹40.00",
        "Parking",
        "₹80.00",
        "Overstay",
        "₹30.00",
        "Total",
        "₹110.00",
        "Payment method",
        "Payment status",
        "Unpaid",
        "Balance due",
    ):
        assert text in html


@pytest.mark.parametrize("method", ["Cash", "UPI", "Card"])
def test_receipt_shows_paid_method_and_balance(client, booking, attendant, entry, method):
    checkout(booking, attendant, entry)
    Payment.objects.create(charge=booking.charges.get(), method=method, recorded_by=attendant)
    client.force_login(attendant)
    response = client.get(reverse("gate:receipt", args=[booking.booking_ref]))
    assert response.status_code == 200
    assert method in response.content.decode()
    assert "Paid" in response.content.decode()
    assert response.context["paid_total"] == Decimal("40.00")
    assert response.context["balance_due"] == 0


@pytest.mark.parametrize("data", [{}, {"query": "unknown"}])
def test_checkout_displays_form_errors(client, attendant, data):
    client.force_login(attendant)
    response = client.post("/gate/checkout/", data)
    assert response.status_code == 200
    assert response.context["form"].errors


@pytest.mark.parametrize("role", ["Driver", "Admin"])
def test_views_forbid_other_roles(client, booking, role):
    client.force_login(User.objects.create_user(email="other@example.com", role=role))
    for response in (
        client.get("/gate/checkout/"),
        client.post("/gate/checkout/", {"query": booking.booking_ref}),
        client.get(f"/gate/receipt/{booking.booking_ref}/"),
    ):
        assert response.status_code == 403
    assert not Charge.objects.exists()


def test_views_redirect_anonymous_to_login(client, booking):
    for response in (
        client.get("/gate/checkout/"),
        client.post("/gate/checkout/", {"query": booking.booking_ref}),
        client.get(f"/gate/receipt/{booking.booking_ref}/"),
    ):
        assert response.status_code == 302
        assert urlparse(response.url).path == "/accounts/login/"


def test_unknown_or_active_receipt_is_404(client, booking, attendant):
    client.force_login(attendant)
    assert client.get("/gate/receipt/unknown/").status_code == 404
    assert client.get(f"/gate/receipt/{booking.booking_ref}/").status_code == 404


def test_audit_failure_rolls_back_checkout(booking, attendant, entry, monkeypatch):
    def fail_audit(**kwargs):
        raise IntegrityError("Audit insert failed")

    monkeypatch.setattr(AuditLog.objects, "create", fail_audit)
    with pytest.raises(IntegrityError, match="Audit insert failed"):
        checkout(booking, attendant, entry + timedelta(hours=9))
    booking.refresh_from_db()
    assert booking.status == "Active"
    assert booking.exit_time is None
    assert not Charge.objects.exists()


def _checkout_in_thread(barrier, booking, attendant, entry):
    try:
        barrier.wait(timeout=10)
        checkout(booking, attendant, entry)
        return "completed"
    except ValidationError:
        return "refused"
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
def test_concurrent_checkouts_have_one_winner(booking, attendant, entry):
    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: _checkout_in_thread(barrier, booking, attendant, entry), range(2))
        )
    assert sorted(results) == ["completed", "refused"]
    assert Charge.objects.count() == AuditLog.objects.count() == 1


@pytest.mark.parametrize("walk_in", [False, True])
def test_receipt_duration_without_overstay(client, booking, attendant, entry, walk_in):
    booking.is_walk_in = walk_in
    booking.save()
    checkout(booking, attendant, entry + timedelta(minutes=61))
    client.force_login(attendant)
    response = client.get(reverse("gate:receipt", args=[booking.booking_ref]))
    html = response.content.decode()
    assert response.status_code == 200
    assert "1.5 hours" in html
    assert "₹60.00" in html
    assert "Billable overstay" not in html


def test_receipt_partial_payment_keeps_each_charge_status(client, booking, attendant, entry):
    booking.period = DateTimeTZRange(entry, entry + timedelta(hours=2))
    booking.save()
    checkout(booking, attendant, entry + timedelta(minutes=160))
    Payment.objects.create(
        charge=booking.charges.get(kind="Parking"), method="UPI", recorded_by=attendant
    )
    client.force_login(attendant)
    response = client.get(reverse("gate:receipt", args=[booking.booking_ref]))
    assert response.context["total"] == Decimal("110.00")
    assert response.context["paid_total"] == Decimal("80.00")
    assert response.context["balance_due"] == Decimal("30.00")
    rows = response.content.decode().split("<tbody>")[1].split("</tbody>")[0].split("</tr>")
    assert "Parking" in rows[0] and "Paid" in rows[0] and "UPI" in rows[0]
    assert "Overstay" in rows[1] and "Unpaid" in rows[1] and "UPI" not in rows[1]
    audit = AuditLog.objects.get(action="reservation.checked_out")
    assert Decimal(audit.after["overstay_hours"]) == Decimal("0.5")
    assert audit.after["overstay_amount_inr"] == "30.00"
