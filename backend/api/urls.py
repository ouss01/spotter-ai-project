from django.urls import path

from . import views

urlpatterns = [
    path("plan-trip/", views.plan_trip, name="plan-trip"),
    path("health/", views.health, name="health"),
]
