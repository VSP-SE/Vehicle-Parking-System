"""FR-LOTMAP-03: seed PES lots and slots."""

from datetime import time

from django.utils import timezone

from vps.accounts.models import User
from vps.lots.models import Lot, Slot, Tariff
from vps.lots.services import create_lot, create_tariff

PES_LOTS = [
    {
        "name": "PES RR Campus Front Gate",
        "address": "PES University, 100 Feet Ring Road, BSK III Stage, Bengaluru 560085",
        "two_wheeler": 100,
        "standard": 30,
        "ev": 4,
        "accessible": 2,
    },
    {
        "name": "PES RR Campus Back Gate",
        "address": "PES University, 100 Feet Ring Road, BSK III Stage, Bengaluru 560085",
        "two_wheeler": 200,
        "standard": 80,
        "ev": 8,
        "accessible": 4,
    },
    {
        "name": "PES EC Campus Engineering Parking",
        "address": "PES University Electronic City Campus, Hosur Road, Bengaluru 560100",
        "two_wheeler": 180,
        "standard": 70,
        "ev": 8,
        "accessible": 4,
    },
    {
        "name": "PES EC Campus Medical Parking",
        "address": "PES University Electronic City Campus, Hosur Road, Bengaluru 560100",
        "two_wheeler": 80,
        "standard": 50,
        "ev": 6,
        "accessible": 6,
    },
]

_SLOT_SPECS = (
    ("two_wheeler", Slot.SlotType.TWO_WHEELER, "TW"),
    ("standard", Slot.SlotType.STANDARD, "ST"),
    ("ev", Slot.SlotType.EV, "EV"),
    ("accessible", Slot.SlotType.ACCESSIBLE, "AC"),
)
_RATES = {
    Slot.SlotType.TWO_WHEELER: "10.00",
    Slot.SlotType.STANDARD: "30.00",
    Slot.SlotType.EV: "30.00",
    Slot.SlotType.ACCESSIBLE: "20.00",
}


def _tariff_actor(actor=None):
    if actor is not None:
        return actor
    return User.objects.filter(is_active=True, role=User.Role.ADMIN).order_by("pk").first()


def _ensure_tariffs(lot, actor, today):
    """Give each slot type a rate. Without an admin yet (first container start) the seed
    writes the rows directly, as seed_demo_data does; with one, changes go through the
    audited service."""
    priced = set(lot.tariffs.values_list("slot_type", flat=True))
    for slot_type, rate in _RATES.items():
        if slot_type in priced:
            continue
        if actor is None:
            Tariff.objects.create(
                lot=lot, slot_type=slot_type, hourly_rate_inr=rate, effective_from=today
            )
        else:
            create_tariff(
                lot=lot,
                slot_type=slot_type,
                hourly_rate_inr=rate,
                effective_from=today,
                actor=actor,
                today=today,
            )


def seed_pes_lots(actor=None, today=None) -> list[Lot]:
    names = [spec["name"] for spec in PES_LOTS]
    actor = _tariff_actor(actor)
    today = today or timezone.localdate()
    existing = Lot.objects.filter(name__in=names)
    for lot in existing:
        _ensure_tariffs(lot, actor, today)
    if set(existing.values_list("name", flat=True)) == set(names):
        return []

    created = []
    for spec in PES_LOTS:
        if Lot.objects.filter(name=spec["name"]).exists():
            continue
        lot = create_lot(
            name=spec["name"],
            address=spec["address"],
            opens_at=time(7),
            closes_at=time(22),
        )
        slots = []
        for count_key, slot_type, prefix in _SLOT_SPECS:
            count = spec[count_key]
            slots.extend(
                Slot(
                    lot=lot,
                    code=f"{prefix}-{index:03d}",
                    slot_type=slot_type,
                    distance_rank=index,
                )
                for index in range(1, count + 1)
            )
        Slot.objects.bulk_create(slots)
        _ensure_tariffs(lot, actor, today)
        created.append(lot)
    return created
