"""FR-LOT-03 – Block a slot for a period (#32)."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from vps.lots.models import Lot, Slot, SlotBlock
from vps.lots.services import block_slot

pytestmark = pytest.mark.django_db


@pytest.fixture
def slot():
    lot = Lot.objects.create(
        name="Lot A", address="1 Ring Road", opens_at="06:00", closes_at="23:00"
    )
    return Slot.objects.create(lot=lot, code="A-01", distance_rank=1)


def test_block_slot_success(slot):
    start = timezone.now() + timedelta(hours=1)
    end = start + timedelta(hours=2)

    block = block_slot(slot=slot, starts_at=start, ends_at=end, reason="Maintenance")

    assert block.pk is not None
    assert block.slot == slot
    assert block.reason == "Maintenance"
    assert block.period.lower == start
    assert block.period.upper == end


def test_block_slot_rejects_empty_reason(slot):
    start = timezone.now() + timedelta(hours=1)
    end = start + timedelta(hours=2)

    with pytest.raises(ValidationError) as exc:
        block_slot(slot=slot, starts_at=start, ends_at=end, reason="   ")
    assert "reason" in exc.value.message_dict


def test_block_slot_rejects_invalid_period(slot):
    start = timezone.now() + timedelta(hours=2)
    end = start - timedelta(hours=1)  # end before start

    with pytest.raises(ValidationError) as exc:
        block_slot(slot=slot, starts_at=start, ends_at=end, reason="Cleaning")
    assert "period" in exc.value.message_dict


def test_block_slot_rejects_overlapping_period(slot):
    start = timezone.now() + timedelta(hours=1)
    end = start + timedelta(hours=3)

    # First block
    block_slot(slot=slot, starts_at=start, ends_at=end, reason="Maintenance")

    # Overlapping block
    with pytest.raises(ValidationError) as exc:
        block_slot(
            slot=slot,
            starts_at=start + timedelta(hours=1),
            ends_at=end + timedelta(hours=1),
            reason="Another reason",
        )
    assert "period" in exc.value.message_dict
    assert "overlap" in str(exc.value).lower()


def test_block_slot_allows_non_overlapping_periods(slot):
    start1 = timezone.now() + timedelta(hours=1)
    end1 = start1 + timedelta(hours=1)

    start2 = end1 + timedelta(minutes=30)
    end2 = start2 + timedelta(hours=1)

    block1 = block_slot(slot=slot, starts_at=start1, ends_at=end1, reason="Morning")
    block2 = block_slot(slot=slot, starts_at=start2, ends_at=end2, reason="Afternoon")

    assert SlotBlock.objects.filter(slot=slot).count() == 2
    assert block1.pk != block2.pk