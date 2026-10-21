"""Driver parking-search routes."""

from django.urls import path

from vps.reservations import views

app_name = "reservations"

urlpatterns = [
    path("search/", views.slot_search, name="search"),
]