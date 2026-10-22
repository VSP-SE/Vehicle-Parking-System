
from django.template.loader import render_to_string


def test_login_template_renders_email_and_password_fields():
    rendered = render_to_string(
        "accounts/login.html",
        {
            "email": "",
            "login_error": "",
        },
    )

    assert "Welcome back" in rendered
    assert 'name="email"' in rendered
    assert 'name="password"' in rendered
    assert 'method="post"' in rendered
    assert "Sign In" in rendered


def test_login_template_displays_authentication_error():
    rendered = render_to_string(
        "accounts/login.html",
        {
            "email": "driver@example.com",
            "login_error": "Invalid e-mail address or password.",
        },
    )

    assert "Invalid e-mail address or password." in rendered
    assert 'value="driver@example.com"' in rendered
