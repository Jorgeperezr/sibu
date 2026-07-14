from django.urls import path

from . import views

app_name = "expediente"

urlpatterns = [
    path("buscar/", views.buscar, name="buscar"),
    path("<int:pk>/", views.detalle, name="detalle"),
]
