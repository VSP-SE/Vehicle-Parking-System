import logging

import pytest
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from vps.accounts.permissions import HasRole, function_required, role_required
from vps.accounts.roles import Function, Role

pytestmark = [pytest.mark.django_db, pytest.mark.urls(__name__)]
PASSWORD = "test-only-secret-password"


def protected(request):
    """A view whose metadata must survive decoration."""
    return HttpResponse("allowed")


class RoleView(APIView):
    permission_classes = (HasRole,)
    allowed_roles = (Role.DRIVER,)

    def get(self, request):
        return Response({"status": "allowed"})


class UnconfiguredView(RoleView):
    allowed_roles = ()


urlpatterns = [
    path("protected/", role_required(Role.DRIVER, Role.GATE_ATTENDANT)(protected)),
    path("reports/", function_required(Function.REPORTS)(protected)),
    path("api/", RoleView.as_view()),
    path("api-unconfigured/", UnconfiguredView.as_view()),
]


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="viewer", password=PASSWORD)


def security_records(caplog):
    return [r for r in caplog.records if r.name == "vps.security"]


@pytest.mark.parametrize("role", ["Driver", "Gate Attendant"])
def test_decorator_allows_role(client, user, role, caplog):
    user.groups.add(Group.objects.get(name=role))
    client.force_login(user)
    with caplog.at_level(logging.WARNING, logger="vps.security"):
        assert client.get("/protected/").status_code == 200
    assert not security_records(caplog)


@pytest.mark.parametrize("role", [None, "Lot Administrator"])
def test_decorator_denies_and_logs_once(client, user, role, caplog):
    if role:
        user.groups.add(Group.objects.get(name=role))
    client.force_login(user)
    with caplog.at_level(logging.WARNING, logger="vps.security"):
        response = client.post("/protected/", {"password": PASSWORD})
    assert response.status_code == 403
    records = security_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    for value in (str(user.pk), "POST", "/protected/", "Driver", "Gate Attendant"):
        assert value in message
    assert PASSWORD not in message
    assert user.password not in message
    assert client.cookies["sessionid"].value not in message


def test_anonymous_redirects_without_logging(client, settings, caplog):
    assert settings.LOGIN_URL == "/accounts/login/"
    with caplog.at_level(logging.WARNING, logger="vps.security"):
        response = client.get("/protected/?page=2")
    assert response.status_code == 302
    assert response.url == "/accounts/login/?next=/protected/%3Fpage%3D2"
    assert not security_records(caplog)


@pytest.mark.parametrize("role,status", [("Driver", 403), ("Lot Administrator", 200)])
def test_function_required_uses_matrix(client, user, role, status):
    user.groups.add(Group.objects.get(name=role))
    client.force_login(user)
    assert client.get("/reports/").status_code == status


@pytest.mark.parametrize("roles", [(), ("Unknown",), (Role.DRIVER, "Unknown"), (None,)])
def test_bad_decoration_raises(roles):
    with pytest.raises(ValueError):
        role_required(*roles)(protected)


def test_decorator_preserves_metadata():
    wrapped = role_required("Driver")(protected)
    assert wrapped.__wrapped__ is protected
    assert wrapped.__name__ == protected.__name__
    assert wrapped.__doc__ == protected.__doc__


@pytest.mark.parametrize(
    "role,url,status,log_count",
    [("Driver", "/api/", 200, 0), ("Gate Attendant", "/api/", 403, 1),
     (None, "/api/", 403, 0), ("Driver", "/api-unconfigured/", 403, 1)],
)
def test_drf_role_permission(client, user, role, url, status, log_count, caplog):
    if role:
        user.groups.add(Group.objects.get(name=role))
        client.force_login(user)
    with caplog.at_level(logging.WARNING, logger="vps.security"):
        response = client.get(url)
    assert response.status_code == status
    records = security_records(caplog)
    assert len(records) == log_count
    if log_count:
        message = records[0].getMessage()
        for value in (str(user.pk), "GET", url):
            assert value in message
        if url == "/api/":
            assert "Driver" in message
        assert records[0].levelno == logging.WARNING
        assert PASSWORD not in message


def test_inactive_user_denied_by_both_permission_interfaces(user, rf, caplog):
    from django.core.exceptions import PermissionDenied

    user.groups.add(Group.objects.get(name="Driver"))
    user.is_active = False
    user.save()
    request = rf.get("/protected/")
    request.user = user
    with caplog.at_level(logging.WARNING, logger="vps.security"):
        with pytest.raises(PermissionDenied):
            role_required(Role.DRIVER)(protected)(request)
        assert not HasRole().has_permission(request, RoleView())
    assert len(security_records(caplog)) == 2


def test_drf_without_role_declaration_denies(user, rf, caplog):
    user.groups.add(Group.objects.get(name="Driver"))
    request = rf.get("/api/")
    request.user = user
    with caplog.at_level(logging.WARNING, logger="vps.security"):
        assert not HasRole().has_permission(request, APIView())
    assert len(security_records(caplog)) == 1
