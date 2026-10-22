"""Driver vehicle routes."""

from django.urls import path

from vps.vehicles import views

app_name = "vehicles"
urlpatterns = [path("", views.register, name="register")]
