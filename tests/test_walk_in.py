"""FR-GATE-03 / TC-12: walk-ins occupy a suitable slot until local closing time."""

import re
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.urls import reverse
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.gate import services
from vps.lots.models import Lot, Slot, SlotBlock
from vps.reservations.models import Reservation
from vps.reservations.services import NO_SLOT, free_slots
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def attendant():
    return User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)


@pytest.fixture
def lot():
    return Lot.objects.create(
        name="Lot A", address="Ring Road", opens_at=time(6), closes_at=time(23)
    )


@pytest.fixture
def now():
    return timezone.make_aware(datetime(2026, 10, 27, 10))


@pytest.fixture
def slot(lot):
    return Slot.objects.create(lot=lot, code="A-01", distance_rank=2)


def register(attendant, lot, now, **kwargs):
    return services.register_walk_in(
        attendant,
        lot,
        kwargs.get("registration_no", "KA05MN4321"),
        kwargs.get("vehicle_type", "Car"),
        now=now,
    )


def test_tc12_uses_slot_free_until_closing(attendant, lot, slot, now):
    nearer = Slot.objects.create(lot=lot, code="A-02", distance_rank=1)
    closing = now.replace(hour=23)
    Reservation.objects.create(
        booking_ref="VPS-261027-9999",
        vehicle_reg_no="KA01AB1234",
        slot=nearer,
        period=DateTimeTZRange(now + timedelta(hours=2), closing),
    )
    booking = register(attendant, lot, now, registration_no=" ka 05 mn 4321 ")
    booking.refresh_from_db()
    assert booking.slot == slot
    assert booking.vehicle_reg_no == "KA05MN4321"
    assert booking.status == "Active"
    assert booking.is_walk_in is True
    assert booking.entry_time == now
    assert booking.driver is None
    assert booking.period == DateTimeTZRange(now, closing)
    assert re.fullmatch(r"VPS-\d{6}-\d{4}", booking.booking_ref)
    vehicle = SimpleNamespace(vehicle_type="Car", owner=None)
    assert free_slots(lot, vehicle, now, closing) == []
    assert not Vehicle.objects.exists()


@pytest.mark.parametrize("occupied_by", ["reservation", "block"])
def test_no_slot_free_for_entire_window(attendant, lot, slot, now, occupied_by):
    period = DateTimeTZRange(now + timedelta(hours=2), now.replace(hour=23))
    if occupied_by == "reservation":
        Reservation.objects.create(
            booking_ref="VPS-261027-9999", vehicle_reg_no="KA01AB1234", slot=slot, period=period
        )
    else:
        SlotBlock.objects.create(slot=slot, period=period, reason="Maintenance")
    with pytest.raises(ValidationError, match=NO_SLOT):
        register(attendant, lot, now)
    assert not Reservation.objects.filter(is_walk_in=True).exists()
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("hour,minute", [(5, 59), (23, 0), (23, 1)])
def test_closed_lot_names_hours(attendant, lot, slot, now, hour, minute):
    with pytest.raises(ValidationError) as error:
        register(attendant, lot, now.replace(hour=hour, minute=minute))
    assert "06:00" in str(error.value)
    assert "23:00" in str(error.value)
    assert not Reservation.objects.exists()


@pytest.mark.parametrize("hour,minute", [(6, 0), (22, 59)])
def test_open_boundary_and_short_walk_in(attendant, lot, slot, now, hour, minute):
    assert register(attendant, lot, now.replace(hour=hour, minute=minute)).status == "Active"


def test_window_uses_local_date_for_utc_input(attendant, lot, slot):
    with timezone.override("Asia/Kolkata"):
        instant = datetime(2026, 10, 27, 1, tzinfo=UTC)
        booking = register(attendant, lot, instant)
        assert booking.period.lower == instant
        assert booking.period.upper == datetime(2026, 10, 27, 17, 30, tzinfo=UTC)


def test_archived_lot_refused(attendant, lot, slot, now):
    lot.is_archived = True
    lot.save()
    with pytest.raises(ValidationError):
        register(attendant, lot, now)
    assert not Reservation.objects.exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("registration_no", "bad"),
        ("registration_no", ""),
        ("vehicle_type", "Truck"),
        ("vehicle_type", ""),
        ("vehicle_type", None),
    ],
)
def test_invalid_inputs_have_field_errors(attendant, lot, slot, now, field, value):
    with pytest.raises(ValidationError) as error:
        register(attendant, lot, now, **{field: value})
    assert field in error.value.message_dict
    assert not Reservation.objects.exists()
    assert not AuditLog.objects.exists()


def test_already_parked_vehicle_in_another_lot_refused(attendant, lot, slot, now):
    other = Lot.objects.create(name="Lot B", address="Other", opens_at=time(6), closes_at=time(23))
    other_slot = Slot.objects.create(lot=other, code="B-01", distance_rank=1)
    Reservation.objects.create(
        booking_ref="VPS-261027-9999",
        vehicle_reg_no="KA05MN4321",
        slot=other_slot,
        period=DateTimeTZRange(now - timedelta(hours=1), now),
        status="Active",
    )
    with pytest.raises(ValidationError, match="This vehicle is already parked."):
        register(attendant, lot, now)
    assert Reservation.objects.count() == 1


@pytest.mark.parametrize(
    "vehicle_type,expected", [("TwoWheeler", "T-01"), ("Car", "A-01"), ("EV", "E-01")]
)
def test_vehicle_type_selects_eligible_slot(attendant, lot, slot, now, vehicle_type, expected):
    for code, kind in [("T-01", "TwoWheeler"), ("X-01", "Accessible"), ("E-01", "EV")]:
        Slot.objects.create(lot=lot, code=code, slot_type=kind, distance_rank=1)
    assert register(attendant, lot, now, vehicle_type=vehicle_type).slot.code == expected


def test_car_never_uses_accessible_slot(attendant, lot, now):
    Slot.objects.create(lot=lot, code="X-01", slot_type="Accessible", distance_rank=1)
    with pytest.raises(ValidationError, match=NO_SLOT):
        register(attendant, lot, now)


def test_audit_records_walk_in(attendant, lot, slot, now):
    booking = register(attendant, lot, now)
    audit = AuditLog.objects.get()
    assert audit.actor == attendant
    assert audit.action == "walkin.registered"
    assert audit.target == f"reservation:{booking.booking_ref}"
    assert audit.before is None
    assert audit.after == {"registration_no": "KA05MN4321", "slot": "A-01", "lot": "Lot A"}


def test_audit_failure_rolls_back_reservation(attendant, lot, slot, now, monkeypatch):
    def fail_audit(**kwargs):
        raise IntegrityError("Audit insert failed")

    monkeypatch.setattr(AuditLog.objects, "create", fail_audit)
    with pytest.raises(IntegrityError, match="Audit insert failed"):
        register(attendant, lot, now)
    assert not Reservation.objects.exists()


@pytest.mark.parametrize("role", ["Driver", "Admin", None])
def test_service_refuses_non_attendants(lot, slot, now, role):
    user = (
        User.objects.create_user(email="other@example.com", role=role) if role else AnonymousUser()
    )
    with pytest.raises(ValidationError):
        register(user, lot, now)
    assert not Reservation.objects.exists()


@pytest.mark.parametrize("role", ["Driver", "Admin"])
def test_view_forbids_other_roles(client, role):
    client.force_login(User.objects.create_user(email="other@example.com", role=role))
    assert client.get("/gate/walk-in/").status_code == 403
    assert client.post("/gate/walk-in/", {}).status_code == 403


def test_view_redirects_anonymous_to_login(client):
    for response in [client.get("/gate/walk-in/"), client.post("/gate/walk-in/", {})]:
        assert response.status_code == 302
        assert urlparse(response.url).path == "/accounts/login/"


def test_page_form_and_active_lots_only(client, attendant, lot):
    Lot.objects.create(
        name="Archived", address="Old", opens_at=time(6), closes_at=time(23), is_archived=True
    )
    client.force_login(attendant)
    assert reverse("gate:walk_in") == "/gate/walk-in/"
    response = client.get("/gate/walk-in/")
    assert response.status_code == 200
    assert list(response.context["form"].fields["lot"].queryset) == [lot]
    html = response.content.decode()
    for text in [
        'name="lot"',
        'name="registration_no"',
        'name="vehicle_type"',
        'name="csrfmiddlewaretoken"',
        'href="/gate/walk-in/"',
        "Walk-in",
    ]:
        assert text in html


def test_view_success_message_and_redirect(client, attendant, lot, slot):
    lot.opens_at, lot.closes_at = time(0), time(23, 59)
    lot.save()
    client.force_login(attendant)
    response = client.post(
        "/gate/walk-in/",
        {"lot": lot.pk, "registration_no": "ka 05 mn 4321", "vehicle_type": "Car"},
        follow=True,
    )
    booking = Reservation.objects.get()
    assert response.redirect_chain == [("/gate/walk-in/", 302)]
    assert (
        f"Walk-in KA05MN4321 parked in A-01 ({booking.booking_ref})." in response.content.decode()
    )


@pytest.mark.parametrize(
    "registration,kind", [("bad", "Car"), ("KA05MN4321", "Truck"), ("KA05MN4321", "Car")]
)
def test_view_errors_preserve_values(client, attendant, lot, registration, kind):
    lot.opens_at, lot.closes_at = time(0), time(23, 59)
    lot.save()
    client.force_login(attendant)
    response = client.post(
        "/gate/walk-in/", {"lot": lot.pk, "registration_no": registration, "vehicle_type": kind}
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert form.errors
    assert form["registration_no"].value() == registration
    assert form["vehicle_type"].value() == kind
    assert str(form["lot"].value()) == str(lot.pk)
    assert not Reservation.objects.exists()
    if registration != "bad" and kind == "Car":
        assert NO_SLOT in response.content.decode()


@pytest.mark.parametrize("lot_value", ["", "invalid", "999999"])
def test_view_invalid_lot_is_form_error(client, attendant, lot_value):
    client.force_login(attendant)
    response = client.post(
        "/gate/walk-in/", {"lot": lot_value, "registration_no": "KA05MN4321", "vehicle_type": "Car"}
    )
    assert response.status_code == 200
    assert "lot" in response.context["form"].errors


@pytest.mark.django_db(transaction=True)
def test_concurrent_walk_ins_for_same_vehicle_have_one_winner(
    attendant, lot, slot, now, monkeypatch
):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from django.db import connections
    from django.db.models import QuerySet

    Slot.objects.create(lot=lot, code="A-02", distance_rank=3)
    start = threading.Barrier(2)
    checked = threading.Event()
    original_exists = QuerySet.exists

    def pause_after_active_check(queryset):
        result = original_exists(queryset)
        if queryset.model is Reservation and not checked.is_set():
            # Give another request time to read the same state before the first inserts.
            checked.set()
            threading.Event().wait(0.2)
        return result

    monkeypatch.setattr(QuerySet, "exists", pause_after_active_check)

    def arrive(_):
        try:
            start.wait(timeout=10)
            return register(attendant, lot, now).status
        except ValidationError as error:
            return error.messages[0]
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(arrive, range(2)))
    assert sorted(results) == sorted(["Active", "This vehicle is already parked."])
    assert Reservation.objects.count() == AuditLog.objects.count() == 1
