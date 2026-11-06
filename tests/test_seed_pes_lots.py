from datetime import date, time
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from vps.accounts.models import User
from vps.lots.models import Slot
from vps.lots.pes import PES_LOTS, seed_pes_lots

pytestmark = pytest.mark.django_db


EXPECTED_TOTALS = {
    "PES RR Campus Front Gate": 136,
    "PES RR Campus Back Gate": 292,
    "PES EC Campus Engineering Parking": 262,
    "PES EC Campus Medical Parking": 142,
}


def test_creates_four_lots_with_exact_mix():
    created = seed_pes_lots(today=date(2026, 11, 6))
    assert len(created) == 4
    for spec in PES_LOTS:
        lot = next(lot for lot in created if lot.name == spec["name"])
        assert lot.slots.filter(slot_type=Slot.SlotType.TWO_WHEELER).count() == spec["two_wheeler"]
        assert lot.slots.filter(slot_type=Slot.SlotType.STANDARD).count() == spec["standard"]
        assert lot.slots.filter(slot_type=Slot.SlotType.EV).count() == spec["ev"]
        assert lot.slots.filter(slot_type=Slot.SlotType.ACCESSIBLE).count() == spec["accessible"]
        assert lot.slots.count() == EXPECTED_TOTALS[lot.name]


def test_idempotent():
    first = seed_pes_lots(today=date(2026, 11, 6))
    second = seed_pes_lots(today=date(2026, 11, 6))
    assert len(first) == 4
    assert second == []
    assert Slot.objects.count() == 832


def test_tariffs_and_hours():
    admin = User.objects.create_user(email="admin@example.com", role=User.Role.ADMIN)
    created = seed_pes_lots(actor=admin, today=date(2026, 11, 6))
    expected_rates = {
        Slot.SlotType.TWO_WHEELER: Decimal("10.00"),
        Slot.SlotType.STANDARD: Decimal("30.00"),
        Slot.SlotType.EV: Decimal("30.00"),
        Slot.SlotType.ACCESSIBLE: Decimal("20.00"),
    }
    for lot in created:
        assert lot.opens_at == time(7)
        assert lot.closes_at == time(22)
        assert lot.tariffs.count() == 4
        for slot_type, rate in expected_rates.items():
            tariff = lot.tariffs.get(slot_type=slot_type)
            assert tariff.hourly_rate_inr == rate
            assert tariff.effective_from == date(2026, 11, 6)


def test_command_output():
    User.objects.create_user(email="admin@example.com", role=User.Role.ADMIN)
    out = StringIO()
    call_command("seed_pes_lots", stdout=out)
    assert "Seeded 4 PES lots (832 slots)." in out.getvalue()

    out = StringIO()
    call_command("seed_pes_lots", stdout=out)
    assert "PES lots already present." in out.getvalue()


def test_tariffs_created_even_without_admin():
    # The web container seeds on start, before anyone has created an admin account.
    created = seed_pes_lots(today=date(2026, 11, 6))
    for lot in created:
        assert lot.tariffs.count() == 4


def test_rerun_backfills_missing_tariffs():
    created = seed_pes_lots(today=date(2026, 11, 6))
    for lot in created:
        lot.tariffs.all().delete()
    assert seed_pes_lots(today=date(2026, 11, 7)) == []
    for lot in created:
        tariff = lot.tariffs.get(slot_type=Slot.SlotType.STANDARD)
        assert tariff.hourly_rate_inr == Decimal("30.00")
        assert tariff.effective_from == date(2026, 11, 7)


def test_command_without_admin_still_prices_lots():
    out = StringIO()
    call_command("seed_pes_lots", stdout=out)
    assert "Seeded 4 PES lots (832 slots)." in out.getvalue()
    assert "skipped tariffs" not in out.getvalue()
