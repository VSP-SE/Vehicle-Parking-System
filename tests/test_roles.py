import pytest
from django.contrib.auth.models import AnonymousUser

from vps.accounts.roles import PERMISSIONS, Function, Role, can, user_roles

pytestmark = pytest.mark.django_db

# Expectations are transcribed independently from SRS Appendix B.3.
MATRIX = [
    (Function.MANAGE_OWN_VEHICLES, (True, False, False)),
    (Function.SEARCH, (True, True, True)),
    (Function.OWN_RESERVATIONS, (True, False, False)),
    (Function.GATE_OPERATIONS, (False, True, False)),
    (Function.CORRECT_TIMES, (False, True, True)),
    (Function.MANAGE_LOTS, (False, False, True)),
    (Function.MANAGE_STAFF, (False, False, True)),
    (Function.REPORTS, (False, False, True)),
]
ROLES = (Role.DRIVER, Role.ATTENDANT, Role.ADMIN)


def test_role_labels_match_srs():
    assert Role.DRIVER.label == "Driver"
    assert len(Role) == 3


@pytest.mark.parametrize("function,allowed", MATRIX)
@pytest.mark.parametrize("index,role", list(enumerate(ROLES)))
def test_permission_matrix(django_user_model, function, allowed, index, role):
    user = django_user_model.objects.create_user(email="matrix@example.com", role=role)
    assert can(user, function) is allowed[index]
    assert (role in PERMISSIONS[function]) is allowed[index]
    assert set(PERMISSIONS) == set(Function)


def test_user_roles_anonymous():
    assert user_roles(AnonymousUser()) == set()
    assert not can(AnonymousUser(), Function.SEARCH)


def test_superuser_flag_grants_nothing(django_user_model):
    user = django_user_model.objects.create_user(
        email="super@example.com", role=Role.DRIVER, is_superuser=True
    )
    assert user_roles(user) == {Role.DRIVER}
    assert not can(user, Function.MANAGE_STAFF)


def test_inactive_user_has_no_roles(django_user_model):
    user = django_user_model.objects.create_user(email="gone@example.com", role=Role.ADMIN)
    user.is_active = False
    user.save()
    assert user_roles(user) == set()
    assert not can(user, Function.SEARCH)


def test_unknown_stored_role_has_no_roles(django_user_model):
    user = django_user_model.objects.create_user(email="odd@example.com")
    user.role = "Unknown"
    assert user_roles(user) == set()
