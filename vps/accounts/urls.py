"""Account routes."""

from django.urls import path

from vps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.sign_in, name="login"),
    path("logout/", views.sign_out, name="logout"),
]
