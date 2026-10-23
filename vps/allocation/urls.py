from django.urls import path

from vps.allocation import views

app_name = "allocation"

urlpatterns = [
    path("search/", views.search, name="search"),
]