"""
Lógica de negocio del módulo de citas.

- Cálculo de disponibilidad a partir de las agendas y bloqueos.
- Reserva con validación de conflictos y de la disponibilidad real del turno.
- Máquina de estados de la cita: solo transiciones válidas, reprogramación
  crea una cita nueva enlazada (audit trail).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.usuarios.models import PerfilProfesional

from .models import Agenda, BloqueoAgenda, Cita

# Transiciones válidas de estado (informe Anexo A)
TRANSICIONES = {
    Cita.Estado.RESERVADA: {
        Cita.Estado.CONFIRMADA,
        Cita.Estado.EN_ESPERA,
        Cita.Estado.CANCELADA,
        Cita.Estado.REPROGRAMADA,
        Cita.Estado.NO_ASISTIO,
    },
    Cita.Estado.CONFIRMADA: {
        Cita.Estado.EN_ESPERA,
        Cita.Estado.CANCELADA,
        Cita.Estado.REPROGRAMADA,
        Cita.Estado.NO_ASISTIO,
    },
    Cita.Estado.EN_ESPERA: {Cita.Estado.EN_ATENCION, Cita.Estado.NO_ASISTIO, Cita.Estado.CANCELADA},
    Cita.Estado.EN_ATENCION: {Cita.Estado.ATENDIDA},
    Cita.Estado.ATENDIDA: set(),
    Cita.Estado.NO_ASISTIO: set(),
    Cita.Estado.CANCELADA: set(),
    Cita.Estado.REPROGRAMADA: set(),
}

ESTADOS_ACTIVOS = {
    Cita.Estado.RESERVADA,
    Cita.Estado.CONFIRMADA,
    Cita.Estado.EN_ESPERA,
    Cita.Estado.EN_ATENCION,
}


def _en_bloqueo(profesional: PerfilProfesional, inicio: datetime, fin: datetime) -> bool:
    return BloqueoAgenda.objects.filter(
        profesional=profesional,
        fecha_inicio__lt=fin,
        fecha_fin__gt=inicio,
    ).exists()


def turnos_disponibles(
    profesional: PerfilProfesional, servicio: Servicio, fecha: date
) -> list[datetime]:
    """Turnos libres del profesional para la fecha dada."""
    agendas = Agenda.objects.filter(
        profesional=profesional,
        servicio=servicio,
        dia_semana=fecha.weekday(),
        activa=True,
        vigente_desde__lte=fecha,
    ).filter(models_q_vigente_hasta(fecha))

    ocupados = set(
        Cita.objects.filter(
            profesional=profesional,
            fecha_hora__date=fecha,
            estado__in=ESTADOS_ACTIVOS,
        ).values_list("fecha_hora", flat=True)
    )

    libres = []
    for agenda in agendas:
        for turno in agenda.generar_turnos(fecha):
            fin = turno + timedelta(minutes=agenda.duracion_turno_min)
            if turno in ocupados:
                continue
            if _en_bloqueo(profesional, turno, fin):
                continue
            libres.append(turno)
    return sorted(libres)


def models_q_vigente_hasta(fecha):
    """Q helper: vigente_hasta nulo o >= fecha."""
    from django.db.models import Q

    return Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha)


@transaction.atomic
def reservar_cita(
    *,
    expediente: Expediente,
    servicio: Servicio,
    profesional: PerfilProfesional,
    fecha_hora: datetime,
    duracion_min: int = 20,
    motivo: str = "",
    origen: str = Cita.Origen.VENTANILLA,
    usuario=None,
    cita_origen: Cita | None = None,
) -> Cita:
    """
    Reserva una cita validando: horario en agenda, sin conflicto activo,
    sin superposición con bloqueos. Levanta ValidationError si algo falla.
    """
    if fecha_hora < timezone.now() - timedelta(minutes=1):
        raise ValidationError("No se puede reservar en el pasado.")

    fin = fecha_hora + timedelta(minutes=duracion_min)

    # 1) Verificar que el turno está dentro de alguna agenda vigente ese día
    agendas = Agenda.objects.filter(
        profesional=profesional,
        servicio=servicio,
        dia_semana=fecha_hora.weekday(),
        activa=True,
        vigente_desde__lte=fecha_hora.date(),
        hora_inicio__lte=fecha_hora.time(),
        hora_fin__gte=fin.time(),
    ).filter(models_q_vigente_hasta(fecha_hora.date()))
    if not agendas.exists():
        raise ValidationError("El horario está fuera de la agenda del profesional.")

    # 2) Sin conflicto: la restricción única de BD lo respalda a nivel base
    if Cita.objects.filter(
        profesional=profesional, fecha_hora=fecha_hora, estado__in=ESTADOS_ACTIVOS
    ).exists():
        raise ValidationError("El turno ya está ocupado.")

    # 3) Sin bloqueo activo
    if _en_bloqueo(profesional, fecha_hora, fin):
        raise ValidationError("El profesional tiene un bloqueo en ese horario.")

    return Cita.objects.create(
        expediente=expediente,
        servicio=servicio,
        profesional=profesional,
        fecha_hora=fecha_hora,
        duracion_min=duracion_min,
        motivo=motivo,
        origen=origen,
        cita_origen=cita_origen,
        creado_por=usuario,
    )


def cambiar_estado(cita: Cita, nuevo: str, usuario=None) -> Cita:
    """
    Aplica una transición de estado si es válida. Registra timestamps
    (llegada_en, atendida_en) cuando corresponde.
    """
    if nuevo == cita.estado:
        return cita
    permitidos = TRANSICIONES.get(cita.estado, set())
    if nuevo not in permitidos:
        raise ValidationError(
            f"Transición inválida: {cita.estado} → {nuevo}. " f"Permitidas: {sorted(permitidos)}"
        )
    cita.estado = nuevo
    if nuevo == Cita.Estado.EN_ESPERA and cita.llegada_en is None:
        cita.llegada_en = timezone.now()
    if nuevo == Cita.Estado.ATENDIDA:
        cita.atendida_en = timezone.now()
    cita.save(update_fields=["estado", "llegada_en", "atendida_en", "actualizado_en"])
    return cita


@transaction.atomic
def reprogramar(
    cita: Cita, nueva_fecha_hora: datetime, usuario=None, motivo_reprogramacion: str = ""
) -> Cita:
    """
    Marca la cita actual como reprogramada y crea una nueva con enlace
    a la original (`cita_origen`).
    """
    if cita.estado not in {Cita.Estado.RESERVADA, Cita.Estado.CONFIRMADA}:
        raise ValidationError("Solo se pueden reprogramar citas reservadas o confirmadas.")
    nueva = reservar_cita(
        expediente=cita.expediente,
        servicio=cita.servicio,
        profesional=cita.profesional,
        fecha_hora=nueva_fecha_hora,
        duracion_min=cita.duracion_min,
        motivo=cita.motivo,
        origen=cita.origen,
        usuario=usuario,
        cita_origen=cita,
    )
    cita.estado = Cita.Estado.REPROGRAMADA
    cita.observaciones = (
        cita.observaciones + "\n" if cita.observaciones else ""
    ) + f"Reprogramada: {motivo_reprogramacion}"
    cita.save(update_fields=["estado", "observaciones", "actualizado_en"])
    return nueva


def cancelar(cita: Cita, motivo: str = "", usuario=None) -> Cita:
    if cita.estado not in {Cita.Estado.RESERVADA, Cita.Estado.CONFIRMADA, Cita.Estado.EN_ESPERA}:
        raise ValidationError("La cita no se puede cancelar en su estado actual.")
    cita.observaciones = (
        cita.observaciones + "\n" if cita.observaciones else ""
    ) + f"Cancelada: {motivo}"
    return cambiar_estado(cita, Cita.Estado.CANCELADA, usuario=usuario)
