from django.urls import path

from . import views

app_name = "citas"

urlpatterns = [
    path("", views.mi_agenda, name="mi_agenda"),
    path("reservar/", views.reservar, name="reservar"),
    path("<int:pk>/estado/", views.cambiar_estado_web, name="cambiar_estado"),
    path("_persona/", views.buscar_persona_json, name="_persona"),
    path("_profesionales/", views.profesionales_json, name="_profesionales"),
]
