import pytest
from django.contrib.auth.models import AnonymousUser, Group

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
ROLES = (Role.DRIVER, Role.GATE_ATTENDANT, Role.LOT_ADMINISTRATOR)


@pytest.mark.parametrize("function,allowed", MATRIX)
@pytest.mark.parametrize("index,role", list(enumerate(ROLES)))
def test_permission_matrix(django_user_model, function, allowed, index, role):
    user = django_user_model.objects.create_user(username="matrix-user")
    user.groups.add(Group.objects.get(name=role))
    assert can(user, function) is allowed[index]
    assert (role in PERMISSIONS[function]) is allowed[index]
    assert set(PERMISSIONS) == set(Function)


def test_user_roles_anonymous():
    assert user_roles(AnonymousUser()) == set()
    assert not can(AnonymousUser(), Function.SEARCH)


def test_user_roles_no_group(django_user_model):
    user = django_user_model.objects.create_user(username="no-group", is_superuser=True)
    assert user_roles(user) == set()
    assert not can(user, Function.MANAGE_STAFF)


def test_user_roles_multiple_and_unrelated_groups(django_user_model):
    user = django_user_model.objects.create_user(username="multi")
    user.groups.add(
        Group.objects.get(name="Driver"),
        Group.objects.get(name="Gate Attendant"),
        Group.objects.create(name="Unrelated"),
    )
    assert user_roles(user) == {Role.DRIVER, Role.GATE_ATTENDANT}
    user.is_active = False
    user.save()
    assert user_roles(user) == set()
    assert not can(user, Function.SEARCH)


def test_migrate_creates_role_groups():
    assert set(Group.objects.values_list("name", flat=True)) == {
        "Driver", "Gate Attendant", "Lot Administrator",
    }


def test_role_group_seeding_is_idempotent():
    from vps.accounts.apps import create_role_groups

    create_role_groups(sender=None)
    assert Group.objects.filter(name__in=["Driver", "Gate Attendant", "Lot Administrator"]).count() == 3
