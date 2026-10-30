"""FR-BILL-01 / TC-33: Lot Administrators set dated tariffs; charges use the one in force at entry."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.gate.services import checkout_vehicle
from vps.lots import services
from vps.lots.models import Lot, Slot, Tariff
from vps.reservations.models import Reservation

pytestmark = pytest.mark.django_db
TODAY = date(2026, 10, 28)


@pytest.fixture
def admin():
    return User.objects.create_user(email="admin@example.com", role=User.Role.ADMIN)


@pytest.fixture
def lot():
    return Lot.objects.create(
        name="Lot A", address="Ring Road", opens_at=time(6), closes_at=time(23)
    )


def create(lot, admin, rate="40.00", day=TODAY, slot_type="Standard"):
    return services.create_tariff(
        lot=lot,
        slot_type=slot_type,
        hourly_rate_inr=Decimal(rate),
        effective_from=day,
        actor=admin,
        today=TODAY,
    )


def test_create_tariff_is_saved_and_audited(lot, admin):
    tariff = create(lot, admin)

    assert Tariff.objects.get() == tariff
    log = AuditLog.objects.get(action="tariff.change")
    assert log.actor == admin
    assert log.target == f"lot:{lot.pk}/slot_type:Standard"
    assert log.after == {"hourly_rate_inr": "40.00", "effective_from": "2026-10-28"}


def test_same_lot_type_and_date_is_refused(lot, admin):
    create(lot, admin)
    with pytest.raises(ValidationError) as error:
        create(lot, admin, rate="45.00")
    assert error.value.message_dict == {"effective_from": [services.TARIFF_DUPLICATE_MESSAGE]}
    assert Tariff.objects.count() == 1


def test_backdated_tariff_is_refused(lot, admin):
    with pytest.raises(ValidationError) as error:
        create(lot, admin, day=TODAY - timedelta(days=1))
    assert error.value.message_dict == {"effective_from": [services.TARIFF_IN_PAST_MESSAGE]}
    assert not AuditLog.objects.exists()


def test_archived_lot_is_refused(lot, admin):
    lot.is_archived = True
    lot.save()
    with pytest.raises(ValidationError):
        create(lot, admin)


def test_tc33_charge_uses_tariff_in_force_at_entry(lot, admin):
    """Rs 40 from yesterday, Rs 50 from today: yesterday's car pays 40, today's pays 50."""
    attendant = User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)
    slot = Slot.objects.create(lot=lot, code="A-01", distance_rank=1)
    other = Slot.objects.create(lot=lot, code="A-02", distance_rank=2)
    Tariff.objects.create(
        lot=lot, slot_type="Standard", hourly_rate_inr="40.00", effective_from=TODAY - timedelta(1)
    )
    create(lot, admin, "50.00")
    today_10 = timezone.make_aware(datetime.combine(TODAY, time(10)))

    def parked(ref, slot, entry):
        return Reservation.objects.create(
            booking_ref=ref,
            vehicle_reg_no=f"KA01AB{ref[-4:]}",
            slot=slot,
            period=DateTimeTZRange(entry, entry + timedelta(days=2)),
            status=Reservation.Status.ACTIVE,
            entry_time=entry,
            is_walk_in=True,
        )

    yesterday_car = parked("VPS-261027-0001", slot, today_10 - timedelta(hours=22))
    today_car = parked("VPS-261028-0002", other, today_10)

    checkout_vehicle(
        yesterday_car.booking_ref, attendant, now=yesterday_car.entry_time + timedelta(hours=2)
    )
    checkout_vehicle(today_car.booking_ref, attendant, now=today_10 + timedelta(hours=2))

    assert yesterday_car.charges.get().amount_inr == Decimal("80.00")
    assert today_car.charges.get().amount_inr == Decimal("100.00")


def test_tariff_page_saves_and_lists(client, lot, admin):
    client.force_login(admin)
    today = timezone.localdate()

    page = client.get("/lots/tariffs/")
    response = client.post(
        "/lots/tariffs/save/",
        {
            "lot_id": lot.pk,
            "slot_type": "EV",
            "hourly_rate_inr": "55.50",
            "effective_from": today.isoformat(),
        },
        follow=True,
    )

    assert page.status_code == 200
    assert '<button type="submit" disabled' not in page.content.decode()
    html = response.content.decode()
    assert "Tariff saved: Rs 55.50 per hour for Electric vehicle slots at Lot A" in html
    assert "₹55.50" in html
    assert Tariff.objects.get().slot_type == "EV"


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("hourly_rate_inr", "0", "greater than or equal to 0.01"),
        ("effective_from", "2020-01-01", services.TARIFF_IN_PAST_MESSAGE),
    ],
)
def test_tariff_page_shows_why_a_tariff_was_refused(client, lot, admin, field, value, message):
    client.force_login(admin)
    data = {
        "lot_id": lot.pk,
        "slot_type": "Standard",
        "hourly_rate_inr": "40.00",
        "effective_from": timezone.localdate().isoformat(),
        field: value,
    }
    response = client.post("/lots/tariffs/save/", data)
    assert response.status_code == 200
    assert message in response.content.decode()
    assert not Tariff.objects.exists()


@pytest.mark.parametrize("role", [User.Role.DRIVER, User.Role.ATTENDANT])
def test_tariff_pages_are_admin_only(client, lot, role):
    client.force_login(User.objects.create_user(email="x@example.com", role=role))
    assert client.get("/lots/tariffs/").status_code == 403
    assert client.post("/lots/tariffs/save/", {}).status_code == 403


def test_admin_nav_links_to_tariffs(client, admin):
    client.force_login(admin)
    assert 'href="/lots/tariffs/"' in client.get("/lots/").content.decode()
