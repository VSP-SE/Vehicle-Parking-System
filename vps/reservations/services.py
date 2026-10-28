"""Booking rules: slot search, limits (FR-RES-03) and race-safe reservation (FR-RES-01, 02)."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.models import User
from vps.accounts.roles import Function, can
from vps.allocation.services import allocate_slot_with_retry, eligible_slot_types
from vps.audit.models import AuditLog
from vps.billing.models import Charge
from vps.lots.models import Slot
from vps.reservations.models import Reservation

NO_SLOT = "No slot available for this window"
LIMIT_REACHED = "You already have 2 open reservations. Cancel one before booking another."
UNPAID_CHARGE = "You have an unpaid charge. Pay it before booking again."
MAX_OPEN_RESERVATIONS = 2
MIN_WINDOW = timedelta(minutes=30)
MAX_WINDOW = timedelta(hours=24)
MAX_START_AHEAD = timedelta(days=7)
NO_SHOW_GRACE = timedelta(minutes=15)
NO_SHOW_CHARGE_INR = Decimal("50.00")
LATE_CANCELLATION_CHARGE_INR = Decimal("30.00")


def validate_window(lot, start, end, now=None):
    """FR-SRCH-02: refuse a window that breaks a rule, naming the rule."""
    now = now or timezone.now()
    if end <= start:
        error = "The end time must be after the start time."
    elif start < now:
        error = "The start time cannot be in the past."
    elif start > now + MAX_START_AHEAD:
        error = "The start time cannot be more than 7 days ahead."
    elif end - start < MIN_WINDOW:
        error = "The parking window must be at least 30 minutes."
    elif end - start > MAX_WINDOW:
        error = "The parking window cannot exceed 24 hours."
    else:
        local_start, local_end = timezone.localtime(start), timezone.localtime(end)
        if (
            local_start.date() == local_end.date()
            and lot.opens_at <= local_start.time()
            and local_end.time() <= lot.closes_at
        ):
            return
        error = f"The window must fall within the lot's opening hours ({lot.opens_at:%H:%M} to {lot.closes_at:%H:%M})."
    raise ValidationError({"__all__": error})


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


def _try_book(
    slot,
    driver,
    vehicle,
    period,
    *,
    status=Reservation.Status.RESERVED,
    is_walk_in=False,
    entry_time=None,
):
    """Insert the reservation, or return None when a concurrent booking already holds the slot."""
    pk = _next_reservation_id()
    reservation = Reservation(
        pk=pk,
        booking_ref=f"VPS-{timezone.localdate():%y%m%d}-{pk % 10000:04d}",
        driver=driver,
        vehicle_reg_no=vehicle.registration_no,
        slot=slot,
        period=period,
        status=status,
        is_walk_in=is_walk_in,
        entry_time=entry_time,
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
    if lot.is_archived:
        raise ValidationError({"__all__": "This parking lot is no longer taking bookings."})
    validate_window(lot, start, end)
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


def expire_no_shows(now=None):
    """FR-RES-05: expire Reserved bookings strictly after FR-GATE-01's 15-minute grace.

    Lock each eligible row and skip rows held by another job or a gate check-in.
    Status, no-show charge and audit entry commit together; Expired frees the slot.
    """
    now = now or timezone.now()
    expired = 0
    with transaction.atomic():
        reservations = Reservation.objects.filter(
            status=Reservation.Status.RESERVED,
            period__startswith__lt=now - NO_SHOW_GRACE,
        ).select_for_update(skip_locked=True)
        for reservation in reservations:
            reservation.status = Reservation.Status.EXPIRED
            reservation.save(update_fields=["status"])
            Charge.objects.create(
                reservation=reservation,
                kind=Charge.Kind.NO_SHOW,
                amount_inr=NO_SHOW_CHARGE_INR,
            )
            AuditLog.objects.create(
                actor=None,
                action="reservation.expired",
                target=f"reservation:{reservation.booking_ref}",
                before={"status": Reservation.Status.RESERVED},
                after={"status": Reservation.Status.EXPIRED},
            )
            expired += 1
    return expired



LATE_CANCELLATION_WINDOW = timedelta(minutes=60)


@transaction.atomic
def cancel_reservation(*, driver, reservation_id, now=None):
    """FR-RES-04: cancel a Driver's Reserved booking before it starts; Rs 30 if under 60 min."""
    if not can(driver, Function.OWN_RESERVATIONS):
        raise ValidationError({"__all__": "Only Drivers may cancel their reservations."})
    reservation = Reservation.objects.select_for_update().get(pk=reservation_id, driver=driver)
    if reservation.status != Reservation.Status.RESERVED:
        raise ValidationError({"__all__": "Only Reserved reservations can be cancelled."})
    now = now or timezone.now()
    start = reservation.period.lower
    if now >= start:
        raise ValidationError(
            {"__all__": "Reservations can only be cancelled before their start time."}
        )
    # Exactly 60 minutes before the start is still a free cancellation.
    late = start - now < LATE_CANCELLATION_WINDOW
    if late:
        Charge.objects.create(
            reservation=reservation,
            kind=Charge.Kind.LATE_CANCEL,
            amount_inr=LATE_CANCELLATION_CHARGE_INR,
        )
    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status"])
    AuditLog.objects.create(
        actor=driver,
        action="reservation.cancelled",
        target=f"reservation:{reservation.booking_ref}",
        before={"status": Reservation.Status.RESERVED},
        after={
            "status": Reservation.Status.CANCELLED,
            "late_cancellation_inr": str(LATE_CANCELLATION_CHARGE_INR) if late else "0.00",
        },
    )
    return reservation
