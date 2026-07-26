from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "expediente"

urlpatterns = [
    # La ruta obvia no debe morir en 404: lleva a la búsqueda de expedientes.
    path(
        "", RedirectView.as_view(pattern_name="expediente:buscar", permanent=False), name="indice"
    ),
    path("buscar/", views.buscar, name="buscar"),
    path("<int:pk>/", views.detalle, name="detalle"),
]
