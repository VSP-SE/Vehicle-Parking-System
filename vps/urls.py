"""URL routes for the VPS project."""

from django.contrib import admin
from django.urls import path

from vps.views import healthz

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
]
