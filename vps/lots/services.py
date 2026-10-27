"""Parking-lot business rules, shared by HTTP and non-HTTP callers."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from vps.lots.models import Lot, Slot
from datetime import datetime

from django.contrib.postgres.fields.ranges import DateTimeTZRange

from vps.lots.models import SlotBlock

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
# ---------------------------------------------------------------------------
# Slot creation (FR-LOT-02 / #31)
# ---------------------------------------------------------------------------

DUPLICATE_SLOT_MESSAGE = "A slot with this code already exists in the lot."


def create_slot(*, lot: Lot, code: str, slot_type: str, distance_rank: int) -> Slot:
    """
    Create a slot in the given lot.

    Enforces:
    - code is required and unique within the lot
    - slot_type is one of the allowed choices
    - distance_rank is a positive integer (≥ 1)
    """
    code = (code or "").strip().upper()
    errors = {}

    if not code:
        errors["code"] = "Enter a code for the slot."
    if distance_rank is None or not isinstance(distance_rank, int) or distance_rank < 1:
        errors["distance_rank"] = (
            "Distance rank must be a positive integer (1 is nearest to the exit)."
        )

    if errors:
        raise ValidationError(errors)

    slot = Slot(
        lot=lot,
        code=code,
        slot_type=slot_type,
        distance_rank=distance_rank,
    )

    # Validate field-level rules (choices, max_length, etc.) without DB constraints
    slot.full_clean(validate_constraints=False)

    # Friendly pre-check
    if Slot.objects.filter(lot=lot, code=code).exists():
        raise ValidationError({"code": DUPLICATE_SLOT_MESSAGE})

    try:
        with transaction.atomic():
            slot.save()
    except IntegrityError as error:
        constraint = getattr(
            getattr(error.__cause__, "diag", None), "constraint_name", None
        )
        if constraint == "slot_lot_code_uniq":
            raise ValidationError({"code": DUPLICATE_SLOT_MESSAGE}) from error
        if constraint == "slot_distance_rank_positive":
            raise ValidationError(
                {
                    "distance_rank": (
                        "Distance rank must be a positive integer "
                        "(1 is nearest to the exit)."
                    )
                }
            ) from error
        raise

    return slot
OVERLAPPING_BLOCK_MESSAGE = "This slot already has a block that overlaps the requested period."


def block_slot(
    *,
    slot: Slot,
    starts_at: datetime,
    ends_at: datetime,
    reason: str,
) -> SlotBlock:
    """
    Block a slot for the given period with a reason (FR-LOT-03).

    Raises ValidationError if:
    - the period is invalid (end <= start)
    - reason is empty
    - the period overlaps an existing block on the same slot
    """
    reason = (reason or "").strip()
    errors = {}

    if not reason:
        errors["reason"] = "Enter a reason for the block."
    if starts_at is None or ends_at is None:
        errors["period"] = "Both start and end times are required."
    elif ends_at <= starts_at:
        errors["period"] = "End time must be later than start time."

    if errors:
        raise ValidationError(errors)

    period = DateTimeTZRange(starts_at, ends_at)

    # Friendly pre-check for overlapping blocks
    if SlotBlock.objects.filter(slot=slot, period__overlap=period).exists():
        raise ValidationError({"period": OVERLAPPING_BLOCK_MESSAGE})

    block = SlotBlock(slot=slot, period=period, reason=reason)

    try:
        with transaction.atomic():
            block.save()
    except IntegrityError as error:
        constraint = getattr(
            getattr(error.__cause__, "diag", None), "constraint_name", None
        )
        if constraint == "slotblock_period_no_overlap":
            raise ValidationError({"period": OVERLAPPING_BLOCK_MESSAGE}) from error
        raise

    return block