"""Driver parking-search routes."""

from django.urls import path

from vps.reservations import views

app_name = "reservations"

urlpatterns = [
    path("search/", views.slot_search, name="search"),
    path("history/", views.booking_history, name="history"),
    path(
        "confirm/",
        views.confirm_reservation,
        name="confirm",
    ),
    path(
        "confirmation/<str:booking_ref>/",
        views.reservation_confirmation,
        name="confirmation",
    ),
    path("<int:reservation_id>/cancel/", views.cancel_booking, name="cancel"),
]
