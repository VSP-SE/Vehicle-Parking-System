"""URL routes for the VPS project."""

from django.contrib import admin
from django.urls import include, path

from vps.views import healthz

urlpatterns = [
    path("lots/", include("vps.lots.urls")),
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
]
