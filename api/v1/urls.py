"""
Router principal de la API v1.
"""

from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.academico.api import CargaInstitucionalViewSet, consultar_persona
from apps.citas.api import AgendaViewSet, BloqueoAgendaViewSet, CitaViewSet
from apps.expediente.api import ExpedienteViewSet, PersonaViewSet
from apps.farmacia.api import (
    AlertasFarmaciaView,
    LoteViewSet,
    MedicamentoViewSet,
    RecetaViewSet,
)
from apps.laboratorio.api import ExamenViewSet, OrdenLaboratorioViewSet
from apps.medicina.api import AtencionMedicinaViewSet
from apps.odontologia.api import (
    AtencionOdontologiaViewSet,
    CatalogoProcedimientoViewSet,
)

router = DefaultRouter()
router.register("academico/cargas", CargaInstitucionalViewSet, basename="carga")
router.register("personas", PersonaViewSet, basename="persona")
router.register("expedientes", ExpedienteViewSet, basename="expediente")
router.register("citas", CitaViewSet, basename="cita")
router.register("agendas", AgendaViewSet, basename="agenda")
router.register("bloqueos-agenda", BloqueoAgendaViewSet, basename="bloqueo")
router.register("atenciones/medicina", AtencionMedicinaViewSet, basename="atencion-medicina")
router.register("laboratorio/ordenes", OrdenLaboratorioViewSet, basename="orden-lab")
router.register("laboratorio/examenes", ExamenViewSet, basename="examen")
router.register("atenciones/odontologia", AtencionOdontologiaViewSet, basename="atencion-odonto")
router.register("odontologia/catalogo", CatalogoProcedimientoViewSet, basename="catalogo-odonto")
router.register("farmacia/medicamentos", MedicamentoViewSet, basename="medicamento")
router.register("farmacia/lotes", LoteViewSet, basename="lote")
router.register("farmacia/recetas", RecetaViewSet, basename="receta")


def salud(_request):
    return JsonResponse({"servicio": "SIBU API", "version": "v1", "estado": "ok"})


urlpatterns = [
    path("salud/", salud, name="api-salud"),
    path("farmacia/alertas/", AlertasFarmaciaView.as_view(), name="farmacia-alertas"),
    path("personas/<str:cedula>/verificacion/", consultar_persona, name="consultar-persona"),
    *router.urls,
]
