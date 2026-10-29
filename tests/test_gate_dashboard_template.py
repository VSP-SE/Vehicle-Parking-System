"""Gate console template (#47): three keyboard-reachable panels, disabled until wired."""

from django.template.loader import render_to_string


def render(**context):
    return render_to_string("gate/dashboard.html", context)


def test_dashboard_has_labelled_check_in_check_out_and_walk_in_panels():
    html = render()

    for anchor in ('id="check-in"', 'id="check-out"', 'id="walk-in"'):
        assert anchor in html
    for href in ('href="#check-in"', 'href="#check-out"', 'href="#walk-in"'):
        assert href in html
    for field in ("checkin-reference", "checkout-reference", "walkin-registration", "walkin-type"):
        assert f'<label for="{field}">' in html
        assert f'id="{field}"' in html
    assert '<option value="TwoWheeler">' in html


def test_actions_stay_disabled_without_backend_urls():
    html = render()
    assert html.count('<button type="submit" disabled>') == 3


def test_actions_post_to_the_given_urls():
    html = render(checkin_url="/gate/in/", checkout_url="/gate/out/", walkin_url="/gate/walk-in/")

    assert 'action="/gate/in/"' in html
    assert 'action="/gate/out/"' in html
    assert 'action="/gate/walk-in/"' in html
    assert '<button type="submit" disabled>' not in html


def test_errors_are_announced_and_escaped():
    html = render(gate_error="<b>No booking</b>", gate_message="Checked in")

    assert (
        '<div class="message message-error" role="alert">&lt;b&gt;No booking&lt;/b&gt;</div>'
        in html
    )
    assert '<div class="message message-info" role="status">Checked in</div>' in html
