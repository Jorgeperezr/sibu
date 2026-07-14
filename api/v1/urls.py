"""
Router principal de la API v1.

Sprint 1: módulo académico (carga institucional + consulta por cédula).
Los siguientes módulos se registran aquí a medida que se implementan.
"""
from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.academico.api import CargaInstitucionalViewSet, consultar_persona

router = DefaultRouter()
router.register("academico/cargas", CargaInstitucionalViewSet, basename="carga")
# Próximos sprints:
# router.register("personas", PersonaViewSet)          # apps.expediente
# router.register("citas", CitaViewSet)                # apps.citas
# router.register("becas/beneficiarios", BeneficiarioViewSet)  # apps.becas
# router.register("talleres", TallerViewSet)           # apps.talleres


def salud(_request):
    return JsonResponse({"servicio": "SIBU API", "version": "v1", "estado": "ok"})


urlpatterns = [
    path("salud/", salud, name="api-salud"),
    path("personas/<str:cedula>/verificacion/", consultar_persona, name="consultar-persona"),
    *router.urls,
]
