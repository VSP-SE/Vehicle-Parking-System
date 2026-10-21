"""Parking lot administration routes."""

from django.urls import path

from vps.lots import views

app_name = "lots"

urlpatterns = [
    path("", views.lot_list, name="list"),
    path("new/", views.lot_create, name="create"),
    path("<int:pk>/edit/", views.lot_edit, name="edit"),
    path("<int:pk>/archive/", views.lot_archive, name="archive"),
    path("<int:pk>/restore/", views.lot_restore, name="restore"),
]
