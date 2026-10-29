"""Database rules from the schema (#16): constraints that must hold even if application code
has a bug. These need PostgreSQL; SQLite has no range types or exclusion constraints."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.billing.models import Charge
from vps.lots.models import Lot, Slot, SlotBlock
from vps.reservations.models import Reservation
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db
START = timezone.make_aware(datetime(2026, 10, 23, 10, 0))


def window(start_hour, end_hour):
    return DateTimeTZRange(START.replace(hour=start_hour), START.replace(hour=end_hour))


@pytest.fixture
def slot():
    lot = Lot.objects.create(name="Lot A", address="1 Ring Road", opens_at=time(6), closes_at=time(23))
    return Slot.objects.create(lot=lot, code="A-01", distance_rank=1)


def reserve(slot, period, status=Reservation.Status.RESERVED, ref="VPS-261023-0001"):
    return Reservation.objects.create(
        booking_ref=ref, vehicle_reg_no="KA01AB1234", slot=slot, period=period, status=status
    )


def assert_rejected(create):
    with pytest.raises(IntegrityError), transaction.atomic():
        create()


# FR-RES-02: no two Reserved or Active reservations may hold one slot for overlapping windows.
@pytest.mark.parametrize("first", [Reservation.Status.RESERVED, Reservation.Status.ACTIVE])
@pytest.mark.parametrize("second", [Reservation.Status.RESERVED, Reservation.Status.ACTIVE])
def test_overlapping_live_reservations_are_rejected(slot, first, second):
    reserve(slot, window(10, 12), first)
    assert_rejected(lambda: reserve(slot, window(11, 13), second, ref="VPS-261023-0002"))


@pytest.mark.parametrize(
    "status",
    [Reservation.Status.CANCELLED, Reservation.Status.EXPIRED, Reservation.Status.COMPLETED],
)
def test_finished_reservations_do_not_hold_the_slot(slot, status):
    reserve(slot, window(10, 12), status)
    reserve(slot, window(10, 12), ref="VPS-261023-0002")
    assert Reservation.objects.count() == 2


def test_back_to_back_windows_are_allowed(slot):
    reserve(slot, window(10, 12))
    reserve(slot, window(12, 14), ref="VPS-261023-0002")
    assert Reservation.objects.count() == 2


def test_overlapping_windows_on_different_slots_are_allowed(slot):
    other = Slot.objects.create(lot=slot.lot, code="A-02", distance_rank=2)
    reserve(slot, window(10, 12))
    reserve(other, window(10, 12), ref="VPS-261023-0002")
    assert Reservation.objects.count() == 2


def test_overlapping_blocks_on_one_slot_are_rejected(slot):
    SlotBlock.objects.create(slot=slot, period=window(8, 12), reason="Resurfacing")
    assert_rejected(
        lambda: SlotBlock.objects.create(slot=slot, period=window(11, 14), reason="Paint")
    )


# FR-LOT-02: distance rank is a positive integer.
def test_distance_rank_must_be_positive(slot):
    assert_rejected(lambda: Slot.objects.create(lot=slot.lot, code="A-09", distance_rank=0))


# FR-VEH-03: registration numbers are unique among active vehicles only.
def test_registration_unique_among_active_vehicles():
    owner = User.objects.create_user(email="driver@example.com")
    car = Vehicle.objects.create(owner=owner, registration_no="KA01AB1234", vehicle_type="Car")
    assert_rejected(
        lambda: Vehicle.objects.create(
            owner=owner, registration_no="KA01AB1234", vehicle_type="Car"
        )
    )
    car.is_active = False
    car.save()
    Vehicle.objects.create(owner=owner, registration_no="KA01AB1234", vehicle_type="Car")
    assert Vehicle.objects.filter(registration_no="KA01AB1234").count() == 2


def test_charge_amount_cannot_be_negative(slot):
    reservation = reserve(slot, window(10, 12))
    assert_rejected(
        lambda: Charge.objects.create(
            reservation=reservation, kind=Charge.Kind.PARKING, amount_inr=Decimal("-1.00")
        )
    )


def test_create_user_normalises_email_and_hashes_password():
    user = User.objects.create_user(email="Driver@EXAMPLE.com", password="s3cret-pass")
    assert user.email == "Driver@example.com"
    assert user.check_password("s3cret-pass")
    assert user.role == User.Role.DRIVER
    assert not user.is_staff
    assert not user.is_superuser
    assert str(user) == "Driver@example.com"


def test_create_user_requires_email():
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user(email="")


def test_create_superuser_sets_flags():
    admin = User.objects.create_superuser(email="root@example.com", password="s3cret-pass")
    assert admin.is_staff
    assert admin.is_superuser


@pytest.mark.parametrize("flag", ["is_staff", "is_superuser"])
def test_create_superuser_rejects_false_flags(flag):
    with pytest.raises(ValueError, match=flag):
        User.objects.create_superuser(email="root@example.com", **{flag: False})


def test_srs_role_labels():
    assert User.Role.ATTENDANT.label == "Gate Attendant"
    assert User.Role.ADMIN.label == "Lot Administrator"


def test_model_strings(slot):
    reservation = reserve(slot, window(10, 12))
    block = SlotBlock.objects.create(slot=slot, period=window(13, 14), reason="Paint")
    assert str(slot) == "Lot A / A-01"
    assert str(reservation) == "VPS-261023-0001"
    assert str(block) == "Block for Lot A / A-01"
    assert START + timedelta(hours=2) == window(10, 12).upper
