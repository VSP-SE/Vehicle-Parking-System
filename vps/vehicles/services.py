"""Vehicle rules, including serialised per-owner active vehicle limits."""

import re

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from vps.accounts.models import User
from vps.accounts.roles import Function, can
from vps.reservations.models import Reservation
from vps.vehicles.models import Vehicle

DUPLICATE_REGISTRATION = "An active vehicle with this registration number already exists."


def normalise_registration(registration_no):
    return "".join(registration_no.split()).upper()


def validate_registration(registration_no):
    if not re.fullmatch(
        r"(?:[A-Z]{2}[0-9]{2}[A-Z]{1,2}[0-9]{4}|[0-9]{2}BH[0-9]{4}[A-Z]{1,2})", registration_no
    ):
        raise ValidationError({"registration_no": "Enter a valid vehicle registration number."})


def add_vehicle(owner, registration_no, vehicle_type, nickname=""):
    if not can(owner, Function.MANAGE_OWN_VEHICLES):
        raise ValidationError({"__all__": "Only Drivers may register vehicles."})
    registration_no = normalise_registration(registration_no)
    validate_registration(registration_no)
    vehicle = Vehicle(
        owner=owner, registration_no=registration_no, vehicle_type=vehicle_type, nickname=nickname
    )
    vehicle.full_clean(validate_constraints=False)
    try:
        with transaction.atomic():
            # Lock a stable parent row, even when the Driver has no vehicles yet.
            User.objects.select_for_update().get(pk=owner.pk)
            if Vehicle.objects.filter(owner=owner, is_active=True).count() >= 5:
                raise ValidationError({"__all__": "You have reached the maximum of 5 vehicles."})
            if Vehicle.objects.filter(registration_no=registration_no, is_active=True).exists():
                raise ValidationError({"registration_no": DUPLICATE_REGISTRATION})
            vehicle.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == (
            "vehicle_active_reg_no_uniq"
        ):
            raise ValidationError({"registration_no": DUPLICATE_REGISTRATION}) from error
        raise
    return vehicle



VEHICLE_HAS_LIVE_BOOKING = (
    "This vehicle cannot be removed because it has an active or reserved booking."
)


def remove_vehicle(vehicle: Vehicle) -> Vehicle:
    """
    Soft-delete a vehicle (set is_active=False).

    Raises ValidationError if the vehicle has any reservation
    in Reserved or Active status (FR-VEH-04).
    """
    if not vehicle.is_active:
        return vehicle  # already removed

    has_live_booking = Reservation.objects.filter(
        vehicle_reg_no=vehicle.registration_no,
        status__in=[Reservation.Status.RESERVED, Reservation.Status.ACTIVE],
    ).exists()

    if has_live_booking:
        raise ValidationError({"__all__": VEHICLE_HAS_LIVE_BOOKING})

    vehicle.is_active = False
    vehicle.save(update_fields=["is_active"])
    return vehicle
