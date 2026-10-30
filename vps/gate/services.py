"""Walk-in registration (FR-GATE-03)."""

from datetime import datetime, timedelta
from decimal import Decimal
from math import ceil
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.models import Q
from django.utils import timezone

from vps.accounts.roles import Function, can
from vps.allocation.services import allocate_slot_with_retry
from vps.audit.models import AuditLog
from vps.billing.models import Charge
from vps.lots.models import Tariff
from vps.reservations.models import Reservation
from vps.reservations.services import NO_SLOT, _try_book, free_slots
from vps.vehicles.models import Vehicle
from vps.vehicles.services import normalise_registration, validate_registration

CHECKOUT_GRACE = timedelta(minutes=10)
OVERSTAY_MULTIPLIER = Decimal("1.5")

CHECKIN_WINDOW = timedelta(minutes=15)
SLOT_STILL_OCCUPIED = (
    "The booked slot is still occupied and no other suitable slot is free. "
    "Ask the driver to wait or direct them to another lot."
)
# For a booking whose vehicle is no longer registered, keep to the booked slot's kind.
_VEHICLE_TYPE_FOR_SLOT = {"TwoWheeler": "TwoWheeler", "EV": "EV"}


def _reallocate_if_occupied(reservation):
    """FR-GATE-07: move the booking off a slot an overstaying vehicle still holds.

    Returns the old slot code when the booking moved, otherwise None. Raises when no
    eligible slot is free for the booking's window and not physically occupied now.
    """
    occupied = set(
        Reservation.objects.filter(
            slot__lot=reservation.slot.lot, status=Reservation.Status.ACTIVE
        ).values_list("slot_id", flat=True)
    )
    if reservation.slot_id not in occupied:
        return None
    vehicle = (
        Vehicle.objects.select_related("owner")
        .filter(owner=reservation.driver, registration_no=reservation.vehicle_reg_no)
        # A removed record can share the plate with a different type; the active one wins.
        .order_by("-is_active", "-pk")
        .first()
    ) or SimpleNamespace(
        vehicle_type=_VEHICLE_TYPE_FOR_SLOT.get(reservation.slot.slot_type, "Car"),
        owner=reservation.driver,
    )
    period = reservation.period
    candidates = [
        slot
        for slot in free_slots(reservation.slot.lot, vehicle, period.lower, period.upper)
        if slot.pk not in occupied
    ]
    old_code = reservation.slot.code

    def try_move(slot):
        try:
            with transaction.atomic():
                Reservation.objects.filter(pk=reservation.pk).update(slot=slot)
        except IntegrityError as error:
            constraint = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
            if constraint != "reservation_slot_period_no_overlap":
                raise
            return False  # A concurrent booking took it; try the next best.
        reservation.slot = slot
        return True

    if not allocate_slot_with_retry(candidates, vehicle, try_move):
        raise ValidationError({"__all__": SLOT_STILL_OCCUPIED})
    return old_code


def check_in_vehicle(query: str, attendant, now=None):
    """
    FR-GATE-01 / FR-GATE-02: Check in a Reserved reservation.

    - Allowed only for status = Reserved
    - Window: 15 minutes before → 15 minutes after the reservation start
    - On success: status → Active, entry_time recorded
    - Too early → raise ValidationError with the earliest allowed time
    """
    if not can(attendant, Function.GATE_OPERATIONS):
        raise ValidationError({"__all__": "Only Gate Attendants may check in vehicles."})

    now = now or timezone.now()
    query = (query or "").strip()
    if not query:
        raise ValidationError({"__all__": "Enter a booking reference or vehicle registration."})

    registration = normalise_registration(query)

    with transaction.atomic():
        candidates = list(
            Reservation.objects.select_for_update()
            .select_related("slot__lot")
            .filter(status=Reservation.Status.RESERVED)
            .filter(
                Q(booking_ref__iexact=query) | Q(vehicle_reg_no=registration)
            )
            .order_by("period")
        )
        # A plate can hold bookings on several days: take the earliest whose window is
        # still open, so tomorrow's booking never hides today's.
        reservation = next(
            (r for r in candidates if now <= r.period.lower + CHECKIN_WINDOW),
            candidates[-1] if candidates else None,
        )

        if reservation is None:
            raise ValidationError(
                {
                    "__all__": (
                        "No Reserved reservation matches that booking reference "
                        "or registration number."
                    )
                }
            )

        start = reservation.period.lower
        earliest = start - CHECKIN_WINDOW
        latest = start + CHECKIN_WINDOW

        if now < earliest:
            # FR-GATE-02 – too early
            local_earliest = timezone.localtime(earliest)
            raise ValidationError(
                {
                    "__all__": (
                        f"Too early to check in. "
                        f"Earliest allowed time is {local_earliest:%d %b %H:%M}."
                    )
                }
            )

        if now > latest:
            raise ValidationError(
                {
                    "__all__": (
                        "The check-in window has closed. "
                        "This reservation can no longer be activated."
                    )
                }
            )

        reservation.reallocated_from = _reallocate_if_occupied(reservation)
        moved = (
            {"reallocated_from": reservation.reallocated_from}
            if reservation.reallocated_from
            else {}
        )

        # Success – activate
        reservation.status = Reservation.Status.ACTIVE
        reservation.entry_time = now
        reservation.save(update_fields=["status", "entry_time"])

        AuditLog.objects.create(
            actor=attendant,
            action="reservation.checked_in",
            target=f"reservation:{reservation.booking_ref}",
            before={"status": Reservation.Status.RESERVED},
            after={
                "status": Reservation.Status.ACTIVE,
                "entry_time": now.isoformat(),
                "slot": reservation.slot.code,
                "vehicle_reg_no": reservation.vehicle_reg_no,
                **moved,
            },
        )

    return reservation


def register_walk_in(attendant, lot, registration_no, vehicle_type, now=None):
    """Allocate a suitable slot until today's closing and record the arrival atomically."""
    if not can(attendant, Function.GATE_OPERATIONS):
        raise ValidationError({"__all__": "Only Gate Attendants may register walk-in vehicles."})
    if lot.is_archived:
        raise ValidationError({"lot": "This parking lot is no longer taking bookings."})
    registration_no = normalise_registration(registration_no)
    validate_registration(registration_no)
    if vehicle_type not in Vehicle.VehicleType.values:
        raise ValidationError({"vehicle_type": "Choose a valid vehicle type."})

    now = now or timezone.now()
    local_now = timezone.localtime(now)
    if not lot.opens_at <= local_now.time() < lot.closes_at:
        raise ValidationError(
            {
                "__all__": f"This parking lot is closed. Opening hours are "
                f"{lot.opens_at:%H:%M} to {lot.closes_at:%H:%M}."
            }
        )
    closing = timezone.make_aware(datetime.combine(local_now.date(), lot.closes_at))
    vehicle = SimpleNamespace(
        registration_no=registration_no, vehicle_type=vehicle_type, owner=None
    )
    period = DateTimeTZRange(now, closing)
    booked = {}
    with transaction.atomic():
        # There is no Vehicle row to lock for a walk-in. Serialise arrivals for this plate
        # across lots, including the first arrival when no reservation row exists yet.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                [f"walkin:{registration_no}"],
            )
        if Reservation.objects.filter(
            vehicle_reg_no=registration_no, status=Reservation.Status.ACTIVE
        ).exists():
            raise ValidationError({"__all__": "This vehicle is already parked."})

        def try_book(slot):
            booked["reservation"] = _try_book(
                slot,
                None,
                vehicle,
                period,
                status=Reservation.Status.ACTIVE,
                is_walk_in=True,
                entry_time=now,
            )
            return booked["reservation"] is not None

        if not allocate_slot_with_retry(free_slots(lot, vehicle, now, closing), vehicle, try_book):
            raise ValidationError({"__all__": NO_SLOT})
        reservation = booked["reservation"]
        AuditLog.objects.create(
            actor=attendant,
            action="walkin.registered",
            target=f"reservation:{reservation.booking_ref}",
            after={
                "registration_no": registration_no,
                "slot": reservation.slot.code,
                "lot": lot.name,
            },
        )
    return reservation


def _billable_hours(duration, minimum_one_hour=False):
    """Round a duration up to 30-minute blocks."""
    if duration.total_seconds() <= 0:
        return Decimal("1.0") if minimum_one_hour else Decimal("0.0")

    half_hours = ceil(duration.total_seconds() / 1800)

    if minimum_one_hour:
        half_hours = max(half_hours, 2)

    return Decimal(half_hours) / Decimal(2)


def _hourly_rate(reservation):
    """Get the latest applicable tariff for the occupied slot."""
    entry_time = reservation.entry_time

    if entry_time is None:
        raise ValidationError(
            {"__all__": "The reservation has no recorded entry time. Check the vehicle in first."}
        )

    entry_date = timezone.localtime(entry_time).date()

    tariff = (
        Tariff.objects.filter(
            lot=reservation.slot.lot,
            slot_type=reservation.slot.slot_type,
            effective_from__lte=entry_date,
        )
        .order_by("-effective_from")
        .first()
    )

    if tariff is None:
        raise ValidationError(
            {"__all__": "No applicable tariff exists for this parking lot and slot type."}
        )

    return tariff.hourly_rate_inr


def checkout_vehicle(query, attendant, now=None):
    """
    FR-GATE-04: complete an Active reservation, calculate charges,
    record exit time, and create an audit entry atomically.
    """
    if not can(attendant, Function.GATE_OPERATIONS):
        raise ValidationError({"__all__": "Only Gate Attendants may check out vehicles."})

    now = now or timezone.now()
    query = query.strip()

    if not query:
        raise ValidationError({"__all__": "Enter a booking reference or vehicle registration."})

    registration = normalise_registration(query)

    with transaction.atomic():
        reservation = (
            Reservation.objects.select_for_update()
            .select_related("slot__lot")
            .filter(status=Reservation.Status.ACTIVE)
            .filter(Q(booking_ref__iexact=query) | Q(vehicle_reg_no=registration))
            .first()
        )

        if reservation is None:
            raise ValidationError(
                {"__all__": "No Active reservation matches that booking reference or registration."}
            )

        if reservation.entry_time is None:
            raise ValidationError({"__all__": "This reservation has no recorded entry time."})

        if now < reservation.entry_time:
            raise ValidationError({"__all__": "Exit time cannot be earlier than entry time."})

        # Lock the reservation before calculating or recording any charges.
        if Charge.objects.filter(
            reservation=reservation,
            kind=Charge.Kind.PARKING,
        ).exists():
            raise ValidationError({"__all__": "A parking charge has already been recorded."})

        rate = _hourly_rate(reservation)

        # The reserved end is the upper bound of the PostgreSQL time range.
        reserved_end = reservation.period.upper
        if not reservation.is_walk_in and (
            reserved_end is None or reserved_end < reservation.entry_time
        ):
            raise ValidationError(
                {"__all__": "The reserved end cannot be before entry or missing."}
            )

        if reservation.is_walk_in:
            parking_end = now
        else:
            parking_end = min(now, reserved_end)

        parking_duration = parking_end - reservation.entry_time
        parking_hours = _billable_hours(
            parking_duration,
            minimum_one_hour=True,
        )
        parking_amount = (rate * parking_hours).quantize(Decimal("0.01"))

        Charge.objects.create(
            reservation=reservation,
            kind=Charge.Kind.PARKING,
            amount_inr=parking_amount,
        )

        overstay_charge = None
        overstay_hours = Decimal("0.0")

        if not reservation.is_walk_in and now > reserved_end + CHECKOUT_GRACE:
            overstay_duration = now - (reserved_end + CHECKOUT_GRACE)
            overstay_hours = _billable_hours(overstay_duration)

            overstay_amount = (rate * OVERSTAY_MULTIPLIER * overstay_hours).quantize(
                Decimal("0.01")
            )

            if overstay_amount > 0:
                overstay_charge = Charge.objects.create(
                    reservation=reservation,
                    kind=Charge.Kind.OVERSTAY,
                    amount_inr=overstay_amount,
                )

        reservation.exit_time = now
        reservation.status = Reservation.Status.COMPLETED
        reservation.save(update_fields=["exit_time", "status"])

        AuditLog.objects.create(
            actor=attendant,
            action="reservation.checked_out",
            target=f"reservation:{reservation.booking_ref}",
            before={"status": Reservation.Status.ACTIVE},
            after={
                "status": Reservation.Status.COMPLETED,
                "vehicle_reg_no": reservation.vehicle_reg_no,
                "slot": reservation.slot.code,
                "exit_time": now.isoformat(),
                "parking_amount_inr": str(parking_amount),
                "overstay_hours": str(overstay_hours),
                "overstay_amount_inr": (
                    str(overstay_charge.amount_inr) if overstay_charge else "0.00"
                ),
            },
        )

    return reservation
