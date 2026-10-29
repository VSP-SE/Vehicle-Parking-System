import pytest
from django.core.exceptions import ValidationError

from vps.accounts.models import User
from vps.vehicles import services
from vps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def driver():
    return User.objects.create_user("driver@example.com", "password")


def payload(**changes):
    return {
        "registration_no": " ka 01 ab 1234 ",
        "vehicle_type": "Car",
        "nickname": "Daily",
    } | changes


def test_add_vehicle(client, driver):
    client.force_login(driver)
    assert client.get("/vehicles/").context["vehicle_count"] == 0
    response = client.post("/vehicles/", payload(), follow=True)
    assert response.status_code == 200
    vehicle = Vehicle.objects.get()
    assert vehicle.registration_no == "KA01AB1234"
    assert vehicle.owner == driver
    assert vehicle.nickname == "Daily"
    assert response.context["vehicle_count"] == 1
    assert "KA01AB1234" in response.content.decode()
    assert "Vehicle registered successfully." in response.content.decode()


@pytest.mark.parametrize("number", ["22BH1234AA", "22bh1234a", "KA01A1234"])
def test_valid_formats(driver, number):
    vehicle = services.add_vehicle(driver, number, "EV")
    assert vehicle.registration_no == number.upper()
    assert services.normalise_registration(" ka 01 ab 1234 ") == "KA01AB1234"
    services.validate_registration(vehicle.registration_no)


@pytest.mark.parametrize(
    "field,value",
    [
        ("registration_no", "BAD"),
        ("registration_no", "KA01ABC1234"),
        ("vehicle_type", "Truck"),
        ("nickname", "x" * 31),
    ],
)
def test_vehicle_rules(client, driver, field, value):
    client.force_login(driver)
    response = client.post("/vehicles/", payload(**{field: value}))
    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert not Vehicle.objects.exists()
    with pytest.raises(ValidationError) as error:
        services.add_vehicle(driver, **payload(**{field: value}))
    assert field in error.value.message_dict


def test_duplicate_and_inactive(client, driver):
    other = User.objects.create_user("other@example.com", "password")
    vehicle = services.add_vehicle(other, "KA01AB1234", "Car")
    client.force_login(driver)
    response = client.post("/vehicles/", payload())
    assert "registration_no" in response.context["form"].errors
    with pytest.raises(ValidationError) as error:
        services.add_vehicle(driver, **payload())
    assert "registration_no" in error.value.message_dict
    vehicle.is_active = False
    vehicle.save()
    assert client.post("/vehicles/", payload()).status_code == 302


def test_vehicle_limit(client, driver):
    for index in range(5):
        services.add_vehicle(driver, f"KA01AB{index:04d}", "TwoWheeler")
    client.force_login(driver)
    response = client.get("/vehicles/")
    assert response.context["vehicle_limit_reached"]
    assert "maximum of 5 vehicles" in response.content.decode()
    assert client.post("/vehicles/", payload()).status_code == 200
    assert Vehicle.objects.count() == 5
    with pytest.raises(ValidationError):
        services.add_vehicle(driver, **payload())


@pytest.mark.parametrize("role", [User.Role.ADMIN, User.Role.ATTENDANT])
def test_forbidden(client, role):
    user = User.objects.create_user(f"{role}@example.com", "password", role=role)
    client.force_login(user)
    assert client.get("/vehicles/").status_code == 403
    assert client.post("/vehicles/", payload()).status_code == 403
    with pytest.raises(ValidationError):
        services.add_vehicle(user, **payload())


def test_anonymous(client):
    assert client.get("/vehicles/").url == "/accounts/login/?next=/vehicles/"


def test_inactive_vehicles_do_not_count_and_list_is_private(client, driver):
    other = User.objects.create_user("other@example.com", "password")
    Vehicle.objects.create(owner=other, registration_no="KA01AB9999", vehicle_type="Car")
    for index in range(5):
        Vehicle.objects.create(
            owner=driver,
            registration_no=f"KA01AB{index:04d}",
            vehicle_type="Car",
            is_active=False,
        )
    client.force_login(driver)
    response = client.post("/vehicles/", payload(), follow=True)
    assert response.context["vehicle_count"] == 1
    assert "KA01AB9999" not in response.content.decode()
    assert "KA01AB0000" not in response.content.decode()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("same_owner", [True, False])
def test_concurrent_additions_respect_limit_and_uniqueness(same_owner):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections

    owners = [
        User.objects.create_user(f"driver{index}@example.com", "password") for index in range(2)
    ]
    if same_owner:
        for index in range(4):
            services.add_vehicle(owners[0], f"KA01AB{index:04d}", "Car")
    barrier = Barrier(2)

    def add(index):
        close_old_connections()
        try:
            owner = User.objects.get(pk=owners[0 if same_owner else index].pk)
            barrier.wait(timeout=10)
            number = f"KA01AB{1000 + index:04d}" if same_owner else "KA01AB1234"
            try:
                services.add_vehicle(owner, number, "Car")
            except ValidationError as error:
                return error.message_dict
            return "saved"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(add, range(2)))
    assert results.count("saved") == 1
    error = next(result for result in results if isinstance(result, dict))
    assert ("__all__" if same_owner else "registration_no") in error
    assert Vehicle.objects.filter(is_active=True).count() == (5 if same_owner else 1)
