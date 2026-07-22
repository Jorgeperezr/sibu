from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.tablero, name="tablero"),
    path("exportar/", views.exportar_csv, name="exportar"),
]
