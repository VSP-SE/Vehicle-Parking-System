"""Parking-lot business rules, shared by HTTP and non-HTTP callers."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from vps.lots.models import Lot

DUPLICATE_MESSAGE = "A parking lot with this name and address already exists. Change either field."
REQUIRED_MESSAGES = {
    "name": "Enter a name for the parking lot.",
    "address": "Enter an address for the parking lot.",
}
EDITABLE_FIELDS = frozenset({"name", "address", "opens_at", "closes_at"})


def validate_hours(opens_at, closes_at):
    """Validate same-day operating hours; missing values get field-level validation."""
    if opens_at is not None and closes_at is not None and closes_at <= opens_at:
        raise ValidationError({"closes_at": "Closing time must be later than opening time."})


def validate_unique_lot(name, address, exclude_pk=None):
    """Reject a second lot with the same name and address, as a name-field error."""
    if name and address:
        duplicates = Lot.objects.filter(name=name.strip(), address=address.strip())
        if duplicates.exclude(pk=exclude_pk).exists():
            raise ValidationError({"name": DUPLICATE_MESSAGE})


def _save_lot(lot):
    errors = {}
    for field in ("name", "address"):
        value = (getattr(lot, field) or "").strip()
        setattr(lot, field, value)
        if not value:
            errors[field] = REQUIRED_MESSAGES[field]
    if errors:
        raise ValidationError(errors)
    # Convert values and enforce field lengths before comparing times or querying duplicates.
    lot.full_clean(validate_constraints=False)
    validate_hours(lot.opens_at, lot.closes_at)
    validate_unique_lot(lot.name, lot.address, lot.pk)
    try:
        # The savepoint keeps the caller's transaction usable if another writer wins the race.
        with transaction.atomic():
            lot.save()
    except IntegrityError as error:
        if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) == (
            "lot_name_address_uniq"
        ):
            raise ValidationError({"name": DUPLICATE_MESSAGE}) from error
        raise
    return lot


def create_lot(*, name, address, opens_at, closes_at):
    return _save_lot(Lot(name=name, address=address, opens_at=opens_at, closes_at=closes_at))


def update_lot(lot, **fields):
    """Update editable lot details, preserving the stored values if validation fails."""
    if fields.keys() - EDITABLE_FIELDS:
        raise ValueError("Only name, address, opens_at and closes_at can be edited.")
    original = {field: getattr(lot, field) for field in EDITABLE_FIELDS}
    for field, value in fields.items():
        setattr(lot, field, value)
    try:
        return _save_lot(lot)
    except ValidationError:
        for field, value in original.items():
            setattr(lot, field, value)
        raise


def archive_lot(lot):
    lot.is_archived = True
    lot.save(update_fields=["is_archived"])
    return lot


def restore_lot(lot):
    lot.is_archived = False
    lot.save(update_fields=["is_archived"])
    return lot
