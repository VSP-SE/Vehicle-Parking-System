
from django.template.loader import render_to_string


def test_vehicle_registration_template_renders_required_fields():
    rendered = render_to_string(
        "vehicles/register.html",
        {
            "registration_no": "",
            "vehicle_type": "",
            "nickname": "",
            "vehicle_count": 0,
            "vehicle_limit_reached": False,
        },
    )

    assert "Add a vehicle" in rendered
    assert 'name="registration_no"' in rendered
    assert 'name="vehicle_type"' in rendered
    assert 'name="nickname"' in rendered
    assert 'value="Car"' in rendered
    assert 'value="TwoWheeler"' in rendered
    assert 'value="EV"' in rendered
    assert 'maxlength="30"' in rendered


def test_vehicle_registration_template_displays_limit():
    rendered = render_to_string(
        "vehicles/register.html",
        {
            "vehicle_count": 5,
            "vehicle_limit_reached": True,
        },
    )

    assert "5 of 5 vehicles registered." in rendered
    assert "maximum of 5 vehicles" in rendered
    assert "name=\"registration_no\"" not in rendered


def test_vehicle_registration_template_displays_error():
    rendered = render_to_string(
        "vehicles/register.html",
        {
            "vehicle_error": "Enter a valid vehicle registration number.",
            "vehicle_count": 0,
            "vehicle_limit_reached": False,
        },
    )

    assert "Enter a valid vehicle registration number." in rendered
