"""FR-LOT-01 services and administrator workflows, including TC-25."""

from datetime import time
from urllib.parse import urlencode

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from vps.accounts.models import User
from vps.lots import services
from vps.lots.models import Lot, Slot

pytestmark = pytest.mark.django_db


@pytest.fixture
def lot_data():
    return {"name": "Lot D", "address": "Main Road", "opens_at": time(6), "closes_at": time(23)}


@pytest.fixture
def lot(lot_data):
    return Lot.objects.create(**lot_data)


@pytest.fixture
def admin_client(client, django_user_model):
    user = django_user_model.objects.create_user(
        email="admin@example.com", password="test-only-password", role=User.Role.ADMIN
    )
    client.force_login(user)
    return client


@pytest.fixture
def post_data():
    return {"name": "Lot D", "address": "Main Road", "opens_at": "06:00", "closes_at": "23:00"}


def test_create_strips_required_fields(lot_data):
    lot_data.update(name=" Lot D ", address=" Main Road ")
    created = services.create_lot(**lot_data)
    created.refresh_from_db()
    assert (created.name, created.address) == ("Lot D", "Main Road")
    assert (created.opens_at, created.closes_at) == (time(6), time(23))
    assert not created.is_archived


@pytest.mark.parametrize("field", ["name", "address"])
@pytest.mark.parametrize("value", ["", "   ", None])
def test_required_service_fields(lot_data, field, value):
    lot_data[field] = value
    with pytest.raises(ValidationError) as error:
        services.create_lot(**lot_data)
    assert field in error.value.message_dict
    assert Lot.objects.count() == 0


@pytest.mark.parametrize("closes_at", [time(5), time(6)])
def test_service_rejects_invalid_hours(lot_data, closes_at):
    lot_data["closes_at"] = closes_at
    with pytest.raises(ValidationError) as error:
        services.create_lot(**lot_data)
    assert error.value.message_dict["closes_at"] == [
        "Closing time must be later than opening time."
    ]
    assert not Lot.objects.exists()


def test_duplicate_pair_is_friendly_and_database_remains_usable(lot, lot_data):
    with pytest.raises(ValidationError) as error:
        services.create_lot(**lot_data)
    assert "already exists" in str(error.value)
    assert Lot.objects.count() == 1
    lot_data["address"] = "Another Road"
    services.create_lot(**lot_data)
    lot_data.update(name="Lot E", address="Main Road")
    services.create_lot(**lot_data)
    assert Lot.objects.count() == 3


def test_update_strips_and_preserves_other_fields(lot):
    services.update_lot(lot, name=" Renamed ", opens_at=time(7))
    lot.refresh_from_db()
    assert lot.name == "Renamed"
    assert lot.address == "Main Road"
    assert lot.opens_at == time(7)
    assert lot.closes_at == time(23)
    services.update_lot(lot, address=" New address ")
    lot.refresh_from_db()
    assert lot.address == "New address"


def test_update_rejects_invalid_hours_without_saving(lot):
    with pytest.raises(ValidationError) as error:
        services.update_lot(lot, opens_at=time(23))
    assert "closes_at" in error.value.message_dict
    lot.refresh_from_db()
    assert lot.opens_at == time(6)


def test_update_duplicate_pair(lot, lot_data):
    other = services.create_lot(**{**lot_data, "name": "Lot E"})
    with pytest.raises(ValidationError, match="already exists"):
        services.update_lot(other, name=lot.name)
    other.refresh_from_db()
    assert other.name == "Lot E"
    services.update_lot(lot, name=lot.name)  # Keeping the same pair is allowed.


def test_archive_restore_idempotent_and_active_queryset(lot):
    services.archive_lot(lot)
    services.archive_lot(lot)
    lot.refresh_from_db()
    assert lot.is_archived
    assert not Lot.objects.active().exists()
    assert Lot.objects.count() == 1
    services.restore_lot(lot)
    services.restore_lot(lot)
    lot.refresh_from_db()
    assert not lot.is_archived
    assert list(Lot.objects.active().filter(name="Lot D")) == [lot]


def test_list_hours_slots_and_placeholder_identity(admin_client, lot):
    Slot.objects.create(lot=lot, code="A1", distance_rank=1)
    response = admin_client.get("/lots/")
    assert response.status_code == 200
    html = response.content.decode()
    for value in ["Lot D", "Main Road", "06:00", "23:00", "admin@example.com", "Admin"]:
        assert value in html
    assert response.context["lots"][0].slot_count == 1
    assert '?archived=1' in html


def test_tc25_create_lot_d(admin_client, post_data):
    response = admin_client.get("/lots/new/")
    assert response.status_code == 200
    assert 'name="csrfmiddlewaretoken"' in response.content.decode()
    response = admin_client.post("/lots/new/", post_data, follow=True)
    assert response.redirect_chain == [("/lots/", 302)]
    assert "created successfully" in response.content.decode()
    created = Lot.objects.get(name="Lot D")
    assert created.opens_at == time(6)
    assert created.closes_at == time(23)


def test_edit(admin_client, lot, post_data):
    response = admin_client.get(f"/lots/{lot.pk}/edit/")
    assert response.status_code == 200
    assert 'value="06:00"' in response.content.decode()
    assert 'value="23:00"' in response.content.decode()
    response = admin_client.post(
        f"/lots/{lot.pk}/edit/", {**post_data, "name": "Lot E"}, follow=True
    )
    assert response.redirect_chain == [("/lots/", 302)]
    assert "updated successfully" in response.content.decode()
    lot.refresh_from_db()
    assert lot.name == "Lot E"


@pytest.mark.parametrize("endpoint", ["new/", "{pk}/edit/"])
@pytest.mark.parametrize(
    "field,value,error",
    [("closes_at", "05:00", "Closing time must be later than opening time."),
     ("closes_at", "06:00", "Closing time must be later than opening time."),
     ("name", "  ", "Enter a name for the parking lot."),
     ("address", "", "Enter an address for the parking lot."),
     ("opens_at", "6 pm", "Enter a time in 24-hour HH:MM format"),
     ("opens_at", "06:00:30", "Enter a time in 24-hour HH:MM format")],
)
def test_invalid_forms_show_field_errors(admin_client, lot, post_data, endpoint, field, value, error):
    response = admin_client.post(
        "/lots/" + endpoint.format(pk=lot.pk), {**post_data, field: value}
    )
    assert response.status_code == 200
    assert error in response.content.decode()
    assert field in response.context["form"].errors
    lot.refresh_from_db()
    assert lot.name == "Lot D"
    assert Lot.objects.count() == 1


def test_duplicate_form_is_friendly(admin_client, lot, post_data):
    response = admin_client.post("/lots/new/", post_data)
    assert response.status_code == 200
    assert "already exists" in response.content.decode()
    assert "name" in response.context["form"].errors
    assert Lot.objects.count() == 1


def test_archived_filter_and_restore(admin_client, lot):
    for _ in range(2):
        response = admin_client.post(f"/lots/{lot.pk}/archive/", follow=True)
        assert response.redirect_chain == [("/lots/", 302)]
        assert "archived successfully" in response.content.decode()
    assert "Lot D" not in admin_client.get("/lots/").content.decode()
    response = admin_client.get("/lots/?archived=1")
    assert "Lot D" in response.content.decode()
    assert list(response.context["lots"]) == [lot]
    for _ in range(2):
        response = admin_client.post(f"/lots/{lot.pk}/restore/", follow=True)
        assert response.redirect_chain == [("/lots/", 302)]
        assert "restored successfully" in response.content.decode()
    assert "Lot D" in admin_client.get("/lots/").content.decode()
    assert "Lot D" not in admin_client.get("/lots/?archived=1").content.decode()


ENDPOINTS = ["", "?archived=1", "new/", "{pk}/edit/", "{pk}/archive/", "{pk}/restore/"]


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("role", [User.Role.DRIVER, User.Role.ATTENDANT])
def test_other_roles_forbidden(client, django_user_model, lot, endpoint, method, role):
    user = django_user_model.objects.create_user(email="other@example.com", role=role)
    client.force_login(user)
    response = getattr(client, method)("/lots/" + endpoint.format(pk=lot.pk))
    assert response.status_code == 403
    assert Lot.objects.count() == 1
    lot.refresh_from_db()
    assert not lot.is_archived


@pytest.mark.parametrize("endpoint", ENDPOINTS)
@pytest.mark.parametrize("method", ["get", "post"])
def test_anonymous_login_redirect(client, lot, endpoint, method):
    url = "/lots/" + endpoint.format(pk=lot.pk)
    response = getattr(client, method)(url)
    assert response.status_code == 302
    assert response.url == "/accounts/login/?" + urlencode({"next": url}, safe="/")


@pytest.mark.parametrize("action", ["archive", "restore"])
def test_state_changes_require_post(admin_client, lot, action):
    assert admin_client.get(f"/lots/{lot.pk}/{action}/").status_code == 405
    lot.refresh_from_db()
    assert not lot.is_archived


@pytest.mark.parametrize("action,method", [("edit", "get"), ("edit", "post"),
                                           ("archive", "post"), ("restore", "post")])
def test_unknown_lot_404(admin_client, action, method):
    assert getattr(admin_client, method)(f"/lots/999999/{action}/").status_code == 404


def test_csrf_required(admin_client, lot):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.cookies = admin_client.cookies
    assert csrf_client.post(f"/lots/{lot.pk}/archive/").status_code == 403
    assert csrf_client.post(f"/lots/{lot.pk}/restore/").status_code == 403
    assert csrf_client.post("/lots/new/", {}).status_code == 403
    assert csrf_client.post(f"/lots/{lot.pk}/edit/", {}).status_code == 403


def test_duplicate_save_race_is_friendly(lot, lot_data, monkeypatch):
    # Simulate a stale precheck, but let PostgreSQL enforce the real unique constraint.
    from vps.lots.models import LotQuerySet

    monkeypatch.setattr(LotQuerySet, "exists", lambda self: False)
    with pytest.raises(ValidationError, match="already exists"):
        services.create_lot(**lot_data)
    assert Lot.objects.count() == 1  # The outer transaction is still usable.


@pytest.mark.parametrize("field", ["name", "address"])
def test_update_required_fields(lot, field):
    with pytest.raises(ValidationError) as error:
        services.update_lot(lot, **{field: "   "})
    assert field in error.value.message_dict
    assert lot.name == "Lot D"
    assert lot.address == "Main Road"


def test_update_does_not_accept_archival_or_unknown_fields(lot):
    with pytest.raises(ValueError):
        services.update_lot(lot, is_archived=True)
    lot.refresh_from_db()
    assert not lot.is_archived


# ---------------------------------------------------------------------------
# Slot creation – FR-LOT-02 / Issue #31
# ---------------------------------------------------------------------------

def test_create_slot_success(lot):
    slot = services.create_slot(
        lot=lot,
        code=" a-01 ",
        slot_type=Slot.SlotType.EV,
        distance_rank=3,
    )
    assert slot.pk is not None
    assert slot.code == "A-01"
    assert slot.slot_type == Slot.SlotType.EV
    assert slot.distance_rank == 3
    assert slot.lot == lot


def test_create_slot_normalises_code(lot):
    slot = services.create_slot(
        lot=lot, code="  b12 ", slot_type="Standard", distance_rank=1
    )
    assert slot.code == "B12"


@pytest.mark.parametrize(
    "slot_type",
    [
        Slot.SlotType.STANDARD,
        Slot.SlotType.TWO_WHEELER,
        Slot.SlotType.EV,
        Slot.SlotType.ACCESSIBLE,
    ],
)
def test_create_slot_all_types(lot, slot_type):
    slot = services.create_slot(
        lot=lot, code=f"T-{slot_type[:3]}", slot_type=slot_type, distance_rank=1
    )
    assert slot.slot_type == slot_type


def test_create_slot_rejects_duplicate_code_in_same_lot(lot):
    services.create_slot(lot=lot, code="C1", slot_type="Standard", distance_rank=1)
    with pytest.raises(ValidationError) as exc:
        services.create_slot(lot=lot, code="c1", slot_type="TwoWheeler", distance_rank=2)
    assert "code" in exc.value.message_dict
    assert "already exists" in str(exc.value)
    assert Slot.objects.filter(lot=lot).count() == 1


def test_create_slot_allows_same_code_in_different_lots(lot):
    other = Lot.objects.create(
        name="Other Lot", address="Other Road", opens_at=time(6), closes_at=time(22)
    )
    services.create_slot(lot=lot, code="X1", slot_type="Standard", distance_rank=1)
    services.create_slot(lot=other, code="X1", slot_type="Standard", distance_rank=1)
    assert Slot.objects.filter(code="X1").count() == 2


@pytest.mark.parametrize("rank", [0, -1, -100])
def test_create_slot_rejects_non_positive_distance_rank(lot, rank):
    with pytest.raises(ValidationError) as exc:
        services.create_slot(
            lot=lot, code="D1", slot_type="Standard", distance_rank=rank
        )
    assert "distance_rank" in exc.value.message_dict


def test_create_slot_rejects_empty_code(lot):
    with pytest.raises(ValidationError) as exc:
        services.create_slot(lot=lot, code="   ", slot_type="Standard", distance_rank=1)
    assert "code" in exc.value.message_dict


def test_create_slot_rejects_invalid_slot_type(lot):
    with pytest.raises(ValidationError):
        services.create_slot(
            lot=lot, code="E1", slot_type="Truck", distance_rank=1
        )