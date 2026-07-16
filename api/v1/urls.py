"""
Router principal de la API v1.
"""

from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.academico.api import CargaInstitucionalViewSet, consultar_persona
from apps.citas.api import AgendaViewSet, BloqueoAgendaViewSet, CitaViewSet
from apps.expediente.api import ExpedienteViewSet, PersonaViewSet
from apps.medicina.api import AtencionMedicinaViewSet

router = DefaultRouter()
router.register("academico/cargas", CargaInstitucionalViewSet, basename="carga")
router.register("personas", PersonaViewSet, basename="persona")
router.register("expedientes", ExpedienteViewSet, basename="expediente")
router.register("citas", CitaViewSet, basename="cita")
router.register("agendas", AgendaViewSet, basename="agenda")
router.register("bloqueos-agenda", BloqueoAgendaViewSet, basename="bloqueo")
router.register("atenciones/medicina", AtencionMedicinaViewSet, basename="atencion-medicina")


def salud(_request):
    return JsonResponse({"servicio": "SIBU API", "version": "v1", "estado": "ok"})


urlpatterns = [
    path("salud/", salud, name="api-salud"),
    path("personas/<str:cedula>/verificacion/", consultar_persona, name="consultar-persona"),
    *router.urls,
]
