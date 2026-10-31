"""Account routes."""

from django.urls import path

from vps.accounts import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.sign_in, name="login"),
    path("logout/", views.sign_out, name="logout"),
    path("staff/create/", views.create_staff, name="create_staff"),
    path("staff/drivers/", views.drivers, name="drivers"),
    path(
        "staff/drivers/<int:user_id>/accessible-permit/",
        views.manage_accessible_permit,
        name="manage_accessible_permit",
    ),
    path(
        "password-reset/",
        views.PasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    path("staff/", views.staff_list, name="staff_list"),
    path(
        "staff/<int:user_id>/deactivate/",
        views.deactivate_staff,
        name="deactivate_staff",
    ),
    path(
        "staff/<int:user_id>/reactivate/",
        views.reactivate_staff,
        name="reactivate_staff",
    ),
]
