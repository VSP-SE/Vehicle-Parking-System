"""Test-only settings; PostgreSQL is the default test database."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-key-never-use-in-production")

from vps.settings import *

if os.environ.get("VPS_TEST_SQLITE") == "1":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
