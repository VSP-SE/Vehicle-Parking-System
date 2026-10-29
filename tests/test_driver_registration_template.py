
from django.template.loader import render_to_string


def test_registration_template_renders_required_fields():
    rendered = render_to_string(
        "accounts/register.html",
        {
            "full_name": "",
            "email": "",
            "mobile": "",
            "registration_error": "",
        },
    )

    assert "Create your Driver account" in rendered
    assert 'name="full_name"' in rendered
    assert 'name="email"' in rendered
    assert 'name="mobile"' in rendered
    assert 'name="password"' in rendered
    assert 'method="post"' in rendered
    assert "Create Driver Account" in rendered


def test_registration_template_shows_duplicate_email_error():
    rendered = render_to_string(
        "accounts/register.html",
        {
            "registration_error": (
                "An account with this e-mail already exists"
            ),
        },
    )

    assert "An account with this e-mail already exists" in rendered


def test_registration_template_has_name_and_mobile_constraints():
    rendered = render_to_string(
        "accounts/register.html",
        {},
    )

    assert 'minlength="2"' in rendered
    assert 'maxlength="100"' in rendered
    assert 'pattern="[6-9][0-9]{9}"' in rendered
    assert 'maxlength="10"' in rendered
