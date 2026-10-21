from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.template.loader import render_to_string
from django.test import RequestFactory

from vps.accounts.models import User


def test_base_template_shows_authenticated_user():
    user = User(
        email="admin@example.com",
        role=User.Role.ADMIN,
    )
    request = RequestFactory().get("/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)

    rendered = render_to_string(
        "base.html",
        {"user": user, "messages": get_messages(request)},
        request=request,
    )

    assert "Vehicle Parking System" in rendered
    assert "admin@example.com" in rendered
    assert user.get_role_display() in rendered


def test_base_template_includes_htmx_and_responsive_styles():
    rendered = render_to_string(
        "base.html",
        {"user": None, "messages": []},
    )

    assert "htmx.org@2.0.4" in rendered
    assert "min-height: 44px" in rendered
    assert "@media (max-width: 480px)" in rendered
    assert 'name="viewport"' in rendered
