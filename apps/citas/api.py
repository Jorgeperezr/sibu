"""
API REST de citas.

Endpoints principales:
- GET/POST /api/v1/citas/
- POST /api/v1/citas/{id}/reprogramar/
- POST /api/v1/citas/{id}/cancelar/
- POST /api/v1/citas/{id}/cambiar_estado/
- GET  /api/v1/citas/disponibilidad/?profesional=&servicio=&fecha=
"""

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.usuarios.models import PerfilProfesional

from . import services
from .models import Agenda, BloqueoAgenda, Cita
from .selectors import proximas_del_expediente
from .serializers import (
    AgendaSerializer,
    BloqueoAgendaSerializer,
    CambioEstadoSerializer,
    CancelacionSerializer,
    CitaSerializer,
    DisponibilidadQuerySerializer,
    ReprogramacionSerializer,
    ReservaCitaSerializer,
)


class AgendaViewSet(viewsets.ModelViewSet):
    queryset = Agenda.objects.select_related("profesional__usuario", "servicio")
    serializer_class = AgendaSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["profesional", "servicio", "dia_semana", "activa"]


class BloqueoAgendaViewSet(viewsets.ModelViewSet):
    queryset = BloqueoAgenda.objects.all()
    serializer_class = BloqueoAgendaSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["profesional"]


class CitaViewSet(viewsets.ModelViewSet):
    queryset = Cita.objects.select_related(
        "expediente__persona", "servicio", "profesional__usuario"
    )
    serializer_class = CitaSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["servicio", "profesional", "estado", "expediente"]

    def create(self, request, *args, **kwargs):
        serializer = ReservaCitaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            cita = services.reservar_cita(
                expediente=Expediente.objects.get(pk=data["expediente"]),
                servicio=Servicio.objects.get(pk=data["servicio"]),
                profesional=PerfilProfesional.objects.get(pk=data["profesional"]),
                fecha_hora=data["fecha_hora"],
                duracion_min=data.get("duracion_min", 20),
                motivo=data.get("motivo", ""),
                origen=data.get("origen", Cita.Origen.VENTANILLA),
                usuario=request.user if request.user.is_authenticated else None,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CitaSerializer(cita).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reprogramar(self, request, pk=None):
        cita = self.get_object()
        s = ReprogramacionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            nueva = services.reprogramar(
                cita,
                s.validated_data["fecha_hora"],
                motivo_reprogramacion=s.validated_data.get("motivo", ""),
                usuario=request.user,
            )
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CitaSerializer(nueva).data)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        cita = self.get_object()
        s = CancelacionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.cancelar(cita, motivo=s.validated_data["motivo"], usuario=request.user)
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CitaSerializer(cita).data)

    @action(detail=True, methods=["post"], url_path="cambiar_estado")
    def cambiar_estado(self, request, pk=None):
        cita = self.get_object()
        s = CambioEstadoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            services.cambiar_estado(cita, s.validated_data["estado"], usuario=request.user)
        except ValidationError as exc:
            return Response({"detalle": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(CitaSerializer(cita).data)

    @action(detail=False, methods=["get"])
    def disponibilidad(self, request):
        s = DisponibilidadQuerySerializer(data=request.query_params)
        s.is_valid(raise_exception=True)
        turnos = services.turnos_disponibles(
            PerfilProfesional.objects.get(pk=s.validated_data["profesional"]),
            Servicio.objects.get(pk=s.validated_data["servicio"]),
            s.validated_data["fecha"],
        )
        return Response({"turnos": [t.isoformat() for t in turnos]})

    @action(detail=False, methods=["get"])
    def proximas(self, request):
        exp_id = request.query_params.get("expediente")
        if not exp_id:
            return Response(
                {"detalle": "Parámetro 'expediente' requerido."}, status=status.HTTP_400_BAD_REQUEST
            )
        citas = proximas_del_expediente(Expediente.objects.get(pk=exp_id))
        return Response(CitaSerializer(citas, many=True).data)
