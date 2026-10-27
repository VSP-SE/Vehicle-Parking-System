"""Account routes."""

from django.urls import path

from vps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.sign_in, name="login"),
    path("logout/", views.sign_out, name="logout"),
    path("staff/create/", views.create_staff, name="create_staff"),
    path(
    "staff/drivers/<int:user_id>/accessible-permit/",
    views.manage_accessible_permit,
    name="manage_accessible_permit"),
]
