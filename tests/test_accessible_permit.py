"""Accessible-parking permits (FR-AUTH-06) and who may use Accessible slots (TC-23)."""

from datetime import time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from vps.accounts import services
from vps.accounts.models import User
from vps.audit.models import AuditLog
from vps.lots.models import Lot, Slot
from vps.reservations.services import NO_SLOT, free_slots, reserve
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db
TOMORROW = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
    days=1
)


@pytest.fixture
def admin():
    return User.objects.create_user(email="admin@example.com", role=User.Role.ADMIN)


def make_driver(email, permit=False):
    driver = User.objects.create_user(
        email=email, full_name=email.split("@")[0].title(), accessible_permit=permit
    )
    car = Vehicle.objects.create(
        owner=driver, registration_no=f"KA01AB{driver.pk:04d}", vehicle_type="Car"
    )
    return driver, car


def test_tc23_only_permit_holders_get_accessible_slots():
    """TC-23: with only Accessible slots free, Q (no permit) gets none and P gets one."""
    lot = Lot.objects.create(
        name="Lot C", address="3 Ring Road", opens_at=time(6), closes_at=time(23)
    )
    Slot.objects.create(lot=lot, code="H-01", slot_type="Accessible", distance_rank=1)
    holder, holder_car = make_driver("p@example.com", permit=True)
    other, other_car = make_driver("q@example.com")
    start, end = TOMORROW.replace(hour=10), TOMORROW.replace(hour=12)

    assert free_slots(lot, other_car, start, end) == []
    with pytest.raises(ValidationError) as error:
        reserve(other, other_car, lot, start, end)
    assert error.value.messages == [NO_SLOT]
    assert reserve(holder, holder_car, lot, start, end).slot.code == "H-01"


@pytest.mark.parametrize("has_permit", [True, False])
def test_admin_sets_permit_and_it_is_audited(admin, has_permit):
    driver, _ = make_driver("d@example.com", permit=not has_permit)

    services.set_accessible_permit(admin, driver, has_permit)

    driver.refresh_from_db()
    assert driver.accessible_permit is has_permit
    entry = AuditLog.objects.get(action="driver.permit_changed")
    assert entry.actor == admin
    assert entry.target == f"user:{driver.pk}"
    assert entry.before == {"accessible_permit": not has_permit}
    assert entry.after == {"accessible_permit": has_permit}


def test_unchanged_permit_writes_no_audit_row(admin):
    driver, _ = make_driver("d@example.com", permit=True)
    services.set_accessible_permit(admin, driver, True)
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("role", [User.Role.DRIVER, User.Role.ATTENDANT])
def test_only_admins_may_set_permits(role):
    actor = User.objects.create_user(email="actor@example.com", role=role)
    driver, _ = make_driver("d@example.com")
    with pytest.raises(ValidationError):
        services.set_accessible_permit(actor, driver, True)
    driver.refresh_from_db()
    assert driver.accessible_permit is False


def test_permits_are_for_drivers_only(admin):
    attendant = User.objects.create_user(email="gate@example.com", role=User.Role.ATTENDANT)
    with pytest.raises(ValidationError):
        services.set_accessible_permit(admin, attendant, True)


def test_driver_list_searches_by_email_and_shows_permits(client, admin):
    make_driver("asha@example.com", permit=True)
    make_driver("ravi@example.com")
    User.objects.create_user(email="asha.gate@example.com", role=User.Role.ATTENDANT)
    client.force_login(admin)

    everyone = client.get("/accounts/staff/drivers/")
    found = client.get("/accounts/staff/drivers/", {"q": "ASHA"})

    assert [d.email for d in everyone.context["drivers"]] == [
        "asha@example.com",
        "ravi@example.com",
    ]
    assert [d.email for d in found.context["drivers"]] == ["asha@example.com"]
    assert "Permit holder" in found.content.decode()


def test_permit_page_updates_and_reports(client, admin):
    driver, _ = make_driver("d@example.com")
    client.force_login(admin)
    url = f"/accounts/staff/drivers/{driver.pk}/accessible-permit/"

    page = client.get(url)
    response = client.post(url, {"accessible_permit": "on"}, follow=True)

    assert "D" in page.content.decode()
    assert "```" not in page.content.decode()
    driver.refresh_from_db()
    assert driver.accessible_permit is True
    assert (
        f"Accessible-parking permit status updated for {driver.email}." in response.content.decode()
    )

    client.post(url, {})
    driver.refresh_from_db()
    assert driver.accessible_permit is False


@pytest.mark.parametrize("role", [User.Role.DRIVER, User.Role.ATTENDANT])
def test_permit_pages_are_admin_only(client, role):
    driver, _ = make_driver("d@example.com")
    client.force_login(User.objects.create_user(email="x@example.com", role=role))
    assert client.get("/accounts/staff/drivers/").status_code == 403
    url = f"/accounts/staff/drivers/{driver.pk}/accessible-permit/"
    assert client.post(url, {"accessible_permit": "on"}).status_code == 403
    driver.refresh_from_db()
    assert driver.accessible_permit is False


def test_permit_pages_redirect_guests_and_404_non_drivers(client, admin):
    assert client.get("/accounts/staff/drivers/").status_code == 302
    client.force_login(admin)
    assert client.get(f"/accounts/staff/drivers/{admin.pk}/accessible-permit/").status_code == 404


def test_admin_header_links_to_drivers(client, admin):
    client.force_login(admin)
    assert 'href="/accounts/staff/drivers/"' in client.get("/lots/").content.decode()
