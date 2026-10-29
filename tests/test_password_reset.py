"""Password reset by e-mail (FR-AUTH-04, SEC-09, TC-22)."""

import logging
import re
from datetime import datetime, timedelta

import pytest
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail

from vps.accounts.models import User

pytestmark = pytest.mark.django_db
OLD, NEW = "Old-pass-2026!", "New-pass-2026!"


@pytest.fixture
def driver():
    return User.objects.create_user(email="driver@example.com", password=OLD)


def request_link(client, email="driver@example.com"):
    response = client.post("/accounts/password-reset/", {"email": email}, follow=True)
    assert "Check your e-mail" in response.content.decode()
    return re.search(r"https?://\S+/accounts/reset/\S+/", mail.outbox[-1].body).group(0)


def set_password(client, link):
    form = client.get(link, follow=True)
    if "Reset link is invalid" in form.content.decode():
        return form
    return client.post(
        form.redirect_chain[-1][0], {"new_password1": NEW, "new_password2": NEW}, follow=True
    )


def test_login_page_links_to_reset(client):
    assert 'href="/accounts/password-reset/"' in client.get("/accounts/login/").content.decode()


def test_tc22_link_resets_password_once(client, driver):
    """TC-22 steps 1-2: the link sets a new password and cannot be used again."""
    link = request_link(client)
    assert mail.outbox[0].to == ["driver@example.com"]
    assert mail.outbox[0].subject == "Vehicle Parking System password reset"

    assert "Password updated" in set_password(client, link).content.decode()
    driver.refresh_from_db()
    assert driver.check_password(NEW)

    assert "Reset link is invalid" in set_password(client, link).content.decode()


def test_tc22_link_expires_after_30_minutes(client, driver, monkeypatch):
    """TC-22 step 3: a link opened 31 minutes later is refused."""
    link = request_link(client)
    later = datetime.now() + timedelta(minutes=31)
    monkeypatch.setattr(PasswordResetTokenGenerator, "_now", lambda self: later)

    assert "Reset link is invalid" in set_password(client, link).content.decode()
    driver.refresh_from_db()
    assert driver.check_password(OLD)


def test_tc22_token_is_not_logged(client, driver, caplog):
    """TC-22 step 4 (SEC-09): the reset token does not appear in application logs."""
    caplog.set_level(logging.DEBUG)
    link = request_link(client)
    token = link.rstrip("/").rsplit("/", 1)[-1]
    set_password(client, link)
    assert token not in caplog.text


def test_unknown_address_gets_same_page_and_no_mail(client):
    client.post("/accounts/password-reset/", {"email": "nobody@example.com"}, follow=True)
    assert mail.outbox == []
