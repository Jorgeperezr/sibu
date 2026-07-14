"""
API del módulo académico.

- CargaInstitucionalViewSet: subir archivo, previsualizar y aplicar la carga.
- consultar_persona: autocompletado por cédula usado por todos los formularios.
"""
import os
import tempfile

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.usuarios.permissions import EsAdministrador

from .models import CargaInstitucional
from .providers import get_provider
from .serializers import (CargaInstitucionalSerializer,
                          ConsultaPersonaSerializer)
from .services import LectorFicha, ProcesadorCarga, hash_archivo


class CargaInstitucionalViewSet(viewsets.ModelViewSet):
    queryset = CargaInstitucional.objects.all()
    serializer_class = CargaInstitucionalSerializer
    permission_classes = [IsAuthenticated, EsAdministrador]
    parser_classes = [MultiPartParser, FormParser]

    def _guardar_temporal(self, archivo) -> str:
        suf = os.path.splitext(archivo.name)[1]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suf)
        for chunk in archivo.chunks():
            tmp.write(chunk)
        tmp.close()
        return tmp.name

    @action(detail=True, methods=["post"])
    def previsualizar(self, request, pk=None):
        """Paso 3-4: valida el archivo cargado y devuelve el resumen sin escribir."""
        carga = self.get_object()
        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response({"detalle": "Adjunte el archivo en el campo 'archivo'."},
                            status=status.HTTP_400_BAD_REQUEST)
        ruta = self._guardar_temporal(archivo)
        try:
            lector = LectorFicha(ruta, carga.formato)
            resultado = ProcesadorCarga(carga, carga.mapeo_columnas).procesar(lector, aplicar=False)
            carga.total_filas = resultado.total
            carga.estado = CargaInstitucional.Estado.VALIDADA
            carga.bitacora = resultado.as_dict()
            carga.save(update_fields=["total_filas", "estado", "bitacora"])
            return Response(resultado.as_dict())
        finally:
            os.unlink(ruta)

    @action(detail=True, methods=["post"])
    def aplicar(self, request, pk=None):
        """Paso 5: aplica la carga (upsert) de forma transaccional."""
        carga = self.get_object()
        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response({"detalle": "Adjunte el archivo en el campo 'archivo'."},
                            status=status.HTTP_400_BAD_REQUEST)
        ruta = self._guardar_temporal(archivo)
        try:
            carga.hash_archivo = hash_archivo(ruta)
            carga.nombre_archivo = archivo.name
            lector = LectorFicha(ruta, carga.formato)
            resultado = ProcesadorCarga(carga, carga.mapeo_columnas).procesar(lector, aplicar=True)
            carga.total_filas = resultado.total
            carga.altas = resultado.altas
            carga.actualizaciones = resultado.actualizaciones
            carga.errores = resultado.errores
            carga.estado = CargaInstitucional.Estado.APLICADA
            carga.bitacora = resultado.as_dict()
            carga.save()
            return Response(resultado.as_dict())
        finally:
            os.unlink(ruta)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def consultar_persona(request, cedula: str):
    """Autocompletado por cédula. Devuelve datos institucionales o 404."""
    datos = get_provider().consultar_persona(cedula)
    if datos is None:
        return Response({"detalle": "Persona no encontrada en la base institucional."},
                        status=status.HTTP_404_NOT_FOUND)
    return Response(ConsultaPersonaSerializer(datos).data)
