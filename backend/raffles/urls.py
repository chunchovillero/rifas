from django.urls import path

from . import views

app_name = "raffles"

urlpatterns = [
    path("", views.home, name="home"),
    path("registro/", views.signup, name="signup"),
    path("panel/", views.dashboard, name="dashboard"),
    path("rifas/nueva/", views.create, name="create"),
    path("rifas/<slug:slug>/", views.detail, name="detail"),
]

