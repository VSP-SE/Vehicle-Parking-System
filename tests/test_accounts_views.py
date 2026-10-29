import pytest
from django.core.exceptions import ValidationError

from vps.accounts import services
from vps.accounts.models import User

pytestmark = pytest.mark.django_db
PASSWORD = "Distinct-Parking!4729"


def details(**changes):
    return {
        "full_name": "Test Driver",
        "email": "driver@example.com",
        "mobile": "9876543210",
        "password": PASSWORD,
    } | changes


def test_registration_signs_in(client):
    assert client.get("/accounts/register/").status_code == 200
    response = client.post("/accounts/register/", details())
    assert response.url == "/"
    user = User.objects.get()
    assert user.role == User.Role.DRIVER
    assert user.check_password(PASSWORD)
    assert client.session["_auth_user_id"] == str(user.pk)
    assert client.get("/").url == "/vehicles/"


@pytest.mark.parametrize(
    "field,value",
    [
        ("full_name", "x"),
        ("full_name", "x" * 101),
        ("email", "invalid"),
        ("mobile", "5876543210"),
        ("mobile", "987654321"),
        ("mobile", "98765432101"),
        ("mobile", "987654321x"),
        ("password", "password"),
    ],
)
def test_registration_rules(client, field, value):
    response = client.post("/accounts/register/", details(**{field: value}))
    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert not User.objects.exists()
    with pytest.raises(ValidationError) as error:
        services.register_driver(**details(**{field: value}))
    assert field in error.value.message_dict


def test_duplicate_email(client):
    services.register_driver(**details())
    response = client.post("/accounts/register/", details())
    assert response.context["form"].errors["email"] == [
        "An account with this e-mail already exists"
    ]
    with pytest.raises(ValidationError, match="An account with this e-mail already exists"):
        services.register_driver(**details())


@pytest.mark.parametrize(
    "role,target",
    [
        (User.Role.DRIVER, "/vehicles/"),
        (User.Role.ADMIN, "/lots/"),
        (User.Role.ATTENDANT, "/reservations/search/"),
    ],
)
def test_login_and_home(client, role, target):
    user = User.objects.create_user("person@example.com", PASSWORD, role=role)
    assert client.get("/accounts/login/").status_code == 200
    response = client.post("/accounts/login/", {"email": user.email, "password": PASSWORD})
    assert response.url == "/"
    assert client.get("/").url == target
    for path in ("/accounts/login/", "/accounts/register/"):
        assert client.get(path).url == "/"
        assert client.post(path, details()).url == "/"
    assert client.get("/accounts/logout/").status_code == 405
    assert client.post("/accounts/logout/").url == "/accounts/login/"
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("email", ["unknown@example.com", "driver@example.com", "invalid"])
def test_failed_login(client, email):
    services.register_driver(**details())
    response = client.post("/accounts/login/", {"email": email, "password": "secret-wrong"})
    assert response.status_code == 200
    assert response.context["login_error"] == "Invalid e-mail or password"
    assert f'value="{email}"' in response.content.decode()
    assert "secret-wrong" not in response.content.decode()


def test_anonymous_home_and_csrf(client):
    assert client.get("/").url == "/accounts/login/"
    from django.test import Client

    assert Client(enforce_csrf_checks=True).post("/accounts/logout/").status_code == 403


def test_registration_preserves_values_and_never_password(client):
    response = client.post("/accounts/register/", details(full_name="x", password="weak-secret"))
    assert response.status_code == 200
    body = response.content.decode()
    assert 'value="x"' in body
    assert 'value="driver@example.com"' in body
    assert 'value="9876543210"' in body
    assert "weak-secret" not in body


@pytest.mark.parametrize("mobile", ["6876543210", "7876543210", "8876543210"])
def test_valid_mobile_prefixes(mobile):
    assert services.register_driver(**details(mobile=mobile)).mobile == mobile


def test_inactive_user_cannot_sign_in(client):
    user = User.objects.create_user("driver@example.com", PASSWORD, is_active=False)
    response = client.post("/accounts/login/", {"email": user.email, "password": PASSWORD})
    assert response.context["login_error"] == "Invalid e-mail or password"
    assert "_auth_user_id" not in client.session


PASSWORD_FOR_NEXT = "Correct-Horse-41"


def test_sign_in_returns_to_safe_next_page(client, django_user_model):
    django_user_model.objects.create_user(
        email="admin@example.com", password=PASSWORD_FOR_NEXT, role=django_user_model.Role.ADMIN
    )
    page = client.get("/accounts/login/?next=/lots/")
    assert 'name="next" value="/lots/"' in page.content.decode()
    response = client.post(
        "/accounts/login/",
        {"email": "admin@example.com", "password": PASSWORD_FOR_NEXT, "next": "/lots/"},
    )
    assert response.status_code == 302
    assert response.url == "/lots/"


def test_sign_in_ignores_external_next(client, django_user_model):
    django_user_model.objects.create_user(email="d@example.com", password=PASSWORD_FOR_NEXT)
    response = client.post(
        "/accounts/login/",
        {"email": "d@example.com", "password": PASSWORD_FOR_NEXT, "next": "https://evil.example/"},
    )
    assert response.status_code == 302
    assert response.url == "/"
