"""URL routes for the VPS project."""

from django.contrib import admin
from django.urls import include, path

from vps.accounts.views import home
from vps.views import healthz

urlpatterns = [
    path("", home, name="home"),
    path("accounts/", include("vps.accounts.urls")),
    path("vehicles/", include("vps.vehicles.urls")),
    path("lots/", include("vps.lots.urls")),
    path("reservations/", include("vps.reservations.urls")),
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
]
