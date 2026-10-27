"""Walk-in registration (FR-GATE-03)."""

from datetime import datetime
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from vps.accounts.roles import Function, can
from vps.allocation.services import allocate_slot_with_retry
from vps.audit.models import AuditLog
from vps.reservations.models import Reservation
from vps.reservations.services import NO_SLOT, _try_book, free_slots
from vps.vehicles.models import Vehicle
from vps.vehicles.services import normalise_registration, validate_registration


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
