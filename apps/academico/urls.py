from django.urls import path

from . import views

app_name = "academico"

urlpatterns = [
    path("carga/asistente/", views.asistente, name="asistente"),
]
