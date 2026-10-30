"""Gate operations routes (FR-GATE-03, 05)."""

from django.urls import path

from vps.gate import views

app_name = "gate"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("check-in/", views.dashboard_checkin, name="checkin"),
    path("dashboard-checkout/", views.dashboard_checkout, name="dashboard_checkout"),
    path("dashboard-walk-in/", views.dashboard_walk_in, name="dashboard_walk_in"),
    path("walk-in/", views.walk_in, name="walk_in"),
    path("checkout/", views.checkout, name="checkout"),
    path("receipt/<str:booking_ref>/", views.receipt, name="receipt"),
    path("payments/", views.payments, name="payments"),
    path("payments/<int:charge_id>/", views.pay_charge, name="pay_charge"),
]
