"""Gate operations routes (FR-GATE-03 to 06)."""

from django.urls import path

from vps.gate import views

app_name = "gate"
urlpatterns = [
    path("walk-in/", views.walk_in, name="walk_in"),
    path("checkout/", views.checkout, name="checkout"),
    path("correct-entry/", views.correct_entry, name="correct_entry"),
    path("receipt/<str:booking_ref>/", views.receipt, name="receipt"),
    path("payments/", views.payments, name="payments"),
    path("payments/<int:charge_id>/", views.pay_charge, name="pay_charge"),
]
