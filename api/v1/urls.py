"""
Router principal de la API v1.

A medida que cada módulo exponga sus ViewSets, se registran aquí. Se deja el
router creado y un endpoint de salud para poder arrancar y documentar la API
desde el inicio del proyecto.
"""
from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# router.register("personas", PersonaViewSet)          # apps.expediente
# router.register("citas", CitaViewSet)                # apps.citas
# router.register("becas/beneficiarios", BeneficiarioViewSet)  # apps.becas
# router.register("talleres", TallerViewSet)           # apps.talleres


def salud(_request):
    return JsonResponse({"servicio": "SIBU API", "version": "v1", "estado": "ok"})


urlpatterns = [
    path("salud/", salud, name="api-salud"),
    *router.urls,
]
