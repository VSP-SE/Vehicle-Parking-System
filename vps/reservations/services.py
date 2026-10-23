"""Booking rules: slot search, limits (FR-RES-03) and race-safe reservation (FR-RES-01, 02)."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.accounts.roles import Function, can
from vps.allocation.services import allocate_slot_with_retry, eligible_slot_types
from vps.billing.models import Charge
from vps.lots.models import Slot
from vps.reservations.models import Reservation

NO_SLOT = "No slot available for this window"
LIMIT_REACHED = "You already have 2 open reservations. Cancel one before booking another."
UNPAID_CHARGE = "You have an unpaid charge. Pay it before booking again."
MAX_OPEN_RESERVATIONS = 2


def free_slots(lot, vehicle, start, end):
    """Slots in the lot that suit the vehicle and are neither blocked nor held for the window."""
    period = DateTimeTZRange(start, end)
    return list(
        Slot.objects.filter(lot=lot, slot_type__in=eligible_slot_types(vehicle))
        .exclude(blocks__period__overlap=period)
        .exclude(
            reservations__status__in=[Reservation.Status.RESERVED, Reservation.Status.ACTIVE],
            reservations__period__overlap=period,
        )
        .select_related("lot")
    )


def check_booking_limits(driver):
    """FR-RES-03: at most 2 Reserved bookings, and nothing unpaid."""
    open_count = Reservation.objects.filter(
        driver=driver, status=Reservation.Status.RESERVED
    ).count()
    if open_count >= MAX_OPEN_RESERVATIONS:
        raise ValidationError({"__all__": LIMIT_REACHED})
    if Charge.objects.filter(reservation__driver=driver, payment__isnull=True).exists():
        raise ValidationError({"__all__": UNPAID_CHARGE})


def _next_reservation_id():
    # Taking the id first lets the booking reference go in with the same insert.
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT nextval(pg_get_serial_sequence(%s, 'id'))", [Reservation._meta.db_table]
        )
        return cursor.fetchone()[0]


def _try_book(slot, driver, vehicle, period):
    """Insert the reservation, or return None when a concurrent booking already holds the slot."""
    pk = _next_reservation_id()
    reservation = Reservation(
        pk=pk,
        booking_ref=f"VPS-{timezone.localdate():%y%m%d}-{pk % 10000:04d}",
        driver=driver,
        vehicle_reg_no=vehicle.registration_no,
        slot=slot,
        period=period,
    )
    try:
        with transaction.atomic():
            reservation.save(force_insert=True)
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == (
            "reservation_slot_period_no_overlap"
        ):
            return None
        raise
    return reservation


def reserve(driver, vehicle, lot, start, end):
    """FR-RES-01: allocate the best free slot and create a Reserved booking.

    The exclusion constraint on (slot, period) decides races (FR-RES-02); a loser moves on to
    the next best slot (FR-ALLOC-03) and gets NO_SLOT once none are left.
    """
    if not can(driver, Function.OWN_RESERVATIONS):
        raise ValidationError({"__all__": "Only Drivers may make reservations."})
    if vehicle.owner_id != driver.pk or not vehicle.is_active:
        raise ValidationError({"__all__": "Choose one of your registered vehicles."})
    period = DateTimeTZRange(start, end)
    booked = {}
    with transaction.atomic():
        # Serialise one Driver's bookings so two tabs cannot both pass the limit check.
        User.objects.select_for_update().get(pk=driver.pk)
        check_booking_limits(driver)

        def try_book(slot):
            booked["reservation"] = _try_book(slot, driver, vehicle, period)
            return booked["reservation"] is not None

        if allocate_slot_with_retry(free_slots(lot, vehicle, start, end), vehicle, try_book):
            return booked["reservation"]
    raise ValidationError({"__all__": NO_SLOT})
