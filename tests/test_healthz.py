from unittest.mock import patch

import pytest
from django.db import OperationalError


def test_healthz_returns_ok(client, db):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("failure_stage", ["connect", "execute"])
def test_healthz_returns_error_when_database_fails(client, failure_stage):
    with patch("vps.views.connection.cursor") as cursor:
        error = OperationalError("test-only database outage")
        if failure_stage == "connect":
            cursor.side_effect = error
        else:
            cursor.return_value.__enter__.return_value.execute.side_effect = error
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {"status": "error"}
    assert b"test-only database outage" not in response.content


def test_healthz_rejects_post(client):
    response = client.post("/healthz")
    assert response.status_code == 405
