"""Booking rules: limits (FR-RES-03) and one winner per slot under concurrency (FR-RES-02)."""

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.billing.models import Charge, Payment
from vps.lots.models import Lot, Slot, SlotBlock
from vps.reservations import services
from vps.reservations.models import Reservation
from vps.vehicles.models import Vehicle

# Tomorrow, so every window is in the future and inside the 7-day search horizon.
START = timezone.localtime().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)


def at(hour):
    return START.replace(hour=hour)


def make_lot(name="Lot A", slots=(("S1", "Standard", 1),)):
    lot = Lot.objects.create(name=name, address="1 Ring Road", opens_at=time(6), closes_at=time(23))
    for code, slot_type, rank in slots:
        Slot.objects.create(lot=lot, code=code, slot_type=slot_type, distance_rank=rank)
    return lot


def make_driver(n=1, vehicle_type="Car"):
    driver = User.objects.create_user(email=f"driver{n}@example.com")
    vehicle = Vehicle.objects.create(
        owner=driver, registration_no=f"KA01AB{n:04d}", vehicle_type=vehicle_type
    )
    return driver, vehicle


def refused(call):
    with pytest.raises(ValidationError) as excinfo:
        call()
    return excinfo.value.message_dict["__all__"]


@pytest.mark.django_db
def test_reserve_creates_reserved_booking_with_reference():
    """TC-06 (FR-RES-01): an EV gets the EV slot first, then the nearest Standard one."""
    lot = make_lot(slots=[("EV1", "EV", 5), ("S2", "Standard", 1), ("S1", "Standard", 1)])
    first, first_ev = make_driver(1, "EV")
    second, second_ev = make_driver(2, "EV")

    booking = services.reserve(first, first_ev, lot, at(10), at(12))
    other = services.reserve(second, second_ev, lot, at(10), at(12))

    assert (booking.slot.code, other.slot.code) == ("EV1", "S1")
    assert booking.status == Reservation.Status.RESERVED
    assert booking.driver == first
    assert booking.vehicle_reg_no == "KA01AB0001"
    assert booking.period == DateTimeTZRange(at(10), at(12))
    assert re.fullmatch(rf"VPS-{timezone.localdate():%y%m%d}-\d{{4}}", booking.booking_ref)
    assert booking.booking_ref != other.booking_ref


@pytest.mark.django_db
def test_free_slots_skip_blocked_occupied_and_ineligible():
    """TC-05 shape: blocked and overlapping-reserved slots are not offered."""
    lot = make_lot(
        slots=[
            ("S1", "Standard", 1),
            ("S2", "Standard", 2),
            ("S3", "Standard", 3),
            ("S4", "Standard", 4),
            ("T1", "TwoWheeler", 1),
        ]
    )
    _, car = make_driver()
    SlotBlock.objects.create(
        slot=lot.slots.get(code="S2"), period=DateTimeTZRange(at(8), at(18)), reason="Paint"
    )
    Reservation.objects.create(
        booking_ref="VPS-261023-0001",
        vehicle_reg_no="KA02CD5678",
        slot=lot.slots.get(code="S3"),
        period=DateTimeTZRange(at(10), at(12)),
    )

    free = services.free_slots(lot, car, at(11), at(13))

    assert sorted(slot.code for slot in free) == ["S1", "S4"]


@pytest.mark.django_db
def test_two_reserved_bookings_block_a_third():
    """TC-08 step 1 (FR-RES-03): the third open booking is refused with the limit reason."""
    lot = make_lot(slots=[("S1", "Standard", 1), ("S2", "Standard", 2), ("S3", "Standard", 3)])
    driver, car = make_driver()
    services.reserve(driver, car, lot, at(10), at(11))
    services.reserve(driver, car, lot, at(12), at(13))

    assert refused(lambda: services.reserve(driver, car, lot, at(14), at(15))) == [
        services.LIMIT_REACHED
    ]
    assert Reservation.objects.count() == 2


@pytest.mark.django_db
def test_unpaid_charge_blocks_booking_until_paid():
    """TC-08 step 2 (FR-RES-03): an unpaid charge is refused with its own reason."""
    lot = make_lot(slots=[("S1", "Standard", 1), ("S2", "Standard", 2)])
    driver, car = make_driver()
    services.reserve(driver, car, lot, at(10), at(11))
    cancelled = services.reserve(driver, car, lot, at(12), at(13))
    cancelled.status = Reservation.Status.CANCELLED
    cancelled.save()
    charge = Charge.objects.create(
        reservation=cancelled, kind=Charge.Kind.NO_SHOW, amount_inr=Decimal("50.00")
    )

    assert refused(lambda: services.reserve(driver, car, lot, at(14), at(15))) == [
        services.UNPAID_CHARGE
    ]

    Payment.objects.create(charge=charge, method=Payment.Method.UPI, recorded_by=driver)
    assert services.reserve(driver, car, lot, at(14), at(15)).status == "Reserved"


@pytest.mark.django_db
def test_finished_bookings_do_not_count_towards_the_limit():
    lot = make_lot(slots=[("S1", "Standard", 1)])
    driver, car = make_driver()
    for hour in (8, 9):
        done = services.reserve(driver, car, lot, at(hour), at(hour + 1))
        done.status = Reservation.Status.COMPLETED
        done.save()
    assert services.reserve(driver, car, lot, at(10), at(11)).slot.code == "S1"


@pytest.mark.django_db
def test_full_lot_gives_no_slot_message():
    lot = make_lot(slots=[("T1", "TwoWheeler", 1)])
    driver, car = make_driver()
    assert refused(lambda: services.reserve(driver, car, lot, at(10), at(11))) == [services.NO_SLOT]


@pytest.mark.django_db
def test_only_the_owner_driver_can_book_a_vehicle():
    lot = make_lot()
    driver, car = make_driver(1)
    other, _ = make_driver(2)
    attendant = User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)

    for user in (other, attendant):
        assert refused(lambda user=user: services.reserve(user, car, lot, at(10), at(11)))
    car.is_active = False
    car.save()
    assert refused(lambda: services.reserve(driver, car, lot, at(10), at(11)))
    assert not Reservation.objects.exists()


def _book_in_thread(barrier, driver, vehicle, lot):
    try:
        barrier.wait()
        return services.reserve(driver, vehicle, lot, at(10), at(11)).booking_ref
    except ValidationError as error:
        return error.message_dict["__all__"][0]
    finally:
        connection.close()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("run", range(20))
def test_exactly_one_booking_wins_the_last_slot(run):
    """TC-07 (FR-RES-02, FR-ALLOC-03): 50 simultaneous requests, 1 free slot, 1 winner."""
    lot = make_lot(name=f"Lot B{run}")
    drivers = [make_driver(n) for n in range(50)]
    barrier = threading.Barrier(len(drivers))

    with ThreadPoolExecutor(max_workers=len(drivers)) as pool:
        results = list(pool.map(lambda pair: _book_in_thread(barrier, *pair, lot), drivers))

    assert sum(result.startswith("VPS-") for result in results) == 1
    assert results.count(services.NO_SLOT) == 49
    assert Reservation.objects.filter(slot__lot=lot).count() == 1


@pytest.mark.django_db
def test_free_slots_judge_each_reservation_on_its_own():
    """A cancelled overlap plus a live booking at another time must not hide the slot."""
    lot = make_lot()
    _, car = make_driver()
    slot = lot.slots.get()
    Reservation.objects.create(
        booking_ref="VPS-261023-0001",
        vehicle_reg_no="KA02CD0001",
        slot=slot,
        period=DateTimeTZRange(at(10), at(12)),
        status=Reservation.Status.CANCELLED,
    )
    Reservation.objects.create(
        booking_ref="VPS-261023-0002",
        vehicle_reg_no="KA02CD0002",
        slot=slot,
        period=DateTimeTZRange(at(15), at(16)),
    )

    assert [s.code for s in services.free_slots(lot, car, at(10), at(12))] == ["S1"]
