"""FR-GATE-06 / TC-31: past entry and exit times after an outage, limited and audited."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.gate import services
from vps.lots.models import Lot, Slot, Tariff
from vps.reservations.models import Reservation

pytestmark = pytest.mark.django_db
LOCAL = "%Y-%m-%dT%H:%M"


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


def refusal(call):
    with pytest.raises(ValidationError) as error:
        call()
    return error.value.message_dict


def test_tc31_step1_past_exit_is_billed_and_audited_with_reason(booking, attendant, entry):
    now = entry + timedelta(hours=5)
    exit_time = now - timedelta(hours=2)

    services.checkout_vehicle(
        booking.booking_ref, attendant, now=now, exit_time=exit_time, reason=" system outage "
    )

    booking.refresh_from_db()
    assert booking.status == Reservation.Status.COMPLETED
    assert booking.exit_time == exit_time
    assert booking.charges.get().amount_inr == Decimal("120.00")
    log = AuditLog.objects.get(action="reservation.checked_out")
    assert log.actor == attendant
    assert log.after["exit_time"] == exit_time.isoformat()
    assert log.after["corrected_from_paper"] is True
    assert log.after["reason"] == "system outage"


def test_tc31_step2_exit_more_than_24_hours_ago_is_refused(booking, attendant, entry):
    now = entry + timedelta(hours=26)
    errors = refusal(
        lambda: services.checkout_vehicle(
            booking.booking_ref,
            attendant,
            now=now,
            exit_time=now - timedelta(hours=25),
            reason="system outage",
        )
    )
    assert errors == {"exit_time": [services.CORRECTION_TOO_OLD]}
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.ACTIVE
    assert not booking.charges.exists()
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("reason", ["", "   "])
def test_tc31_step3_correction_without_reason_is_refused(booking, attendant, entry, reason):
    now = entry + timedelta(hours=5)
    errors = refusal(
        lambda: services.checkout_vehicle(
            booking.booking_ref,
            attendant,
            now=now,
            exit_time=now - timedelta(hours=1),
            reason=reason,
        )
    )
    assert errors == {"reason": [services.REASON_REQUIRED]}
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.ACTIVE


def test_exactly_24_hours_ago_is_allowed(booking, attendant, entry):
    now = entry + timedelta(hours=24)
    services.checkout_vehicle(
        booking.booking_ref, attendant, now=now, exit_time=entry, reason="outage"
    )
    booking.refresh_from_db()
    assert booking.exit_time == entry


def test_future_exit_and_exit_before_entry_are_refused(booking, attendant, entry):
    now = entry + timedelta(hours=3)
    future = refusal(
        lambda: services.checkout_vehicle(
            booking.booking_ref,
            attendant,
            now=now,
            exit_time=now + timedelta(minutes=1),
            reason="x",
        )
    )
    early = refusal(
        lambda: services.checkout_vehicle(
            booking.booking_ref,
            attendant,
            now=now,
            exit_time=entry - timedelta(minutes=1),
            reason="x",
        )
    )
    assert future == {"exit_time": [services.CORRECTION_IN_FUTURE]}
    assert early == {"__all__": ["Exit time cannot be earlier than entry time."]}


def test_ordinary_checkout_is_not_marked_as_corrected(booking, attendant, entry):
    services.checkout_vehicle(booking.booking_ref, attendant, now=entry + timedelta(hours=1))
    log = AuditLog.objects.get(action="reservation.checked_out")
    assert "corrected_from_paper" not in log.after
    assert "reason" not in log.after


def test_entry_correction_moves_entry_back_and_is_audited(booking, attendant, entry):
    now = entry + timedelta(hours=2)
    paper_entry = entry - timedelta(minutes=40)

    services.correct_entry_time(attendant, "ka01ab1234", paper_entry, "Barrier offline", now=now)

    booking.refresh_from_db()
    assert booking.entry_time == paper_entry
    log = AuditLog.objects.get(action="reservation.entry_corrected")
    assert log.actor == attendant
    assert log.target == "reservation:VPS-261027-0001"
    assert datetime.fromisoformat(log.before["entry_time"]) == entry
    assert datetime.fromisoformat(log.after["entry_time"]) == paper_entry
    assert log.after["reason"] == "Barrier offline"

    services.checkout_vehicle(booking.booking_ref, attendant, now=now)
    booking.refresh_from_db()
    # 2 h 40 min from the corrected entry rounds up to 3 h at Rs 40.
    assert booking.charges.get().amount_inr == Decimal("120.00")


def test_entry_correction_rules(booking, attendant, entry):
    now = entry + timedelta(hours=2)
    ref = booking.booking_ref
    assert refusal(lambda: services.correct_entry_time(attendant, ref, entry, "", now=now)) == {
        "reason": [services.REASON_REQUIRED]
    }
    assert refusal(
        lambda: services.correct_entry_time(attendant, ref, now - timedelta(hours=25), "x", now=now)
    ) == {"entry_time": [services.CORRECTION_TOO_OLD]}
    assert refusal(
        lambda: services.correct_entry_time(
            attendant, ref, now + timedelta(minutes=5), "x", now=now
        )
    ) == {"entry_time": [services.CORRECTION_IN_FUTURE]}
    booking.status = Reservation.Status.COMPLETED
    booking.save()
    assert "__all__" in refusal(
        lambda: services.correct_entry_time(attendant, ref, entry, "x", now=now)
    )
    booking.refresh_from_db()
    assert booking.entry_time == entry
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("role", [User.Role.DRIVER, User.Role.ADMIN])
def test_only_attendants_may_correct_times(booking, entry, role):
    user = User.objects.create_user(email="x@example.com", role=role)
    now = entry + timedelta(hours=2)
    with pytest.raises(ValidationError):
        services.correct_entry_time(user, booking.booking_ref, entry, "x", now=now)
    with pytest.raises(ValidationError):
        services.checkout_vehicle(
            booking.booking_ref, user, now=now, exit_time=entry + timedelta(hours=1), reason="x"
        )


def test_checkout_page_accepts_a_paper_exit_time(client, booking, attendant):
    booking.entry_time = timezone.now() - timedelta(hours=3)
    booking.period = DateTimeTZRange(booking.entry_time, booking.entry_time + timedelta(hours=8))
    booking.save()
    exit_time = timezone.localtime() - timedelta(hours=1)
    client.force_login(attendant)

    refused = client.post(
        "/gate/checkout/", {"query": booking.booking_ref, "exit_time": exit_time.strftime(LOCAL)}
    )
    response = client.post(
        "/gate/checkout/",
        {
            "query": booking.booking_ref,
            "exit_time": exit_time.strftime(LOCAL),
            "reason": "system outage",
        },
    )

    assert refused.status_code == 200
    assert services.REASON_REQUIRED in refused.content.decode()
    assert response.status_code == 302
    booking.refresh_from_db()
    assert booking.exit_time == exit_time.replace(second=0, microsecond=0)


def test_checkout_page_refuses_a_reason_without_a_time(client, booking, attendant):
    client.force_login(attendant)
    response = client.post("/gate/checkout/", {"query": booking.booking_ref, "reason": "outage"})
    assert "Enter the exit time this reason is for." in response.content.decode()
    booking.refresh_from_db()
    assert booking.status == Reservation.Status.ACTIVE


def test_entry_correction_page(client, booking, attendant):
    paper_entry = timezone.localtime() - timedelta(hours=2)
    client.force_login(attendant)
    page = client.get("/gate/correct-entry/")

    response = client.post(
        "/gate/correct-entry/",
        {
            "query": booking.booking_ref,
            "entry_time": paper_entry.strftime(LOCAL),
            "reason": "Barrier offline",
        },
        follow=True,
    )

    assert page.status_code == 200
    assert 'href="/gate/correct-entry/"' in page.content.decode()
    booking.refresh_from_db()
    assert booking.entry_time == paper_entry.replace(second=0, microsecond=0)
    assert "Entry time for VPS-261027-0001 corrected" in response.content.decode()


def test_entry_correction_page_is_for_attendants_only(client, booking):
    client.force_login(User.objects.create_user(email="d@example.com"))
    assert client.get("/gate/correct-entry/").status_code == 403
