"""Gate operations routes (FR-GATE-03, 05)."""

from django.urls import path

from vps.gate import views

app_name = "gate"
urlpatterns = [
    path("walk-in/", views.walk_in, name="walk_in"),
    path("payments/", views.payments, name="payments"),
    path("payments/<int:charge_id>/", views.pay_charge, name="pay_charge"),
]
