"""Consultas de lectura de citas y agendas."""
from datetime import date, timedelta

from django.utils import timezone

from apps.usuarios.models import PerfilProfesional

from .models import Cita
from .services import ESTADOS_ACTIVOS

# Tolerancia por defecto de la ventana del recordatorio.
# 15 min corresponde a la frecuencia recomendada de ejecución del task en
# Celery Beat: cada tick abarca exactamente una ventana sin solapamiento.
TOLERANCIA_MINUTOS_DEFECTO = 15


def citas_del_dia(profesional: PerfilProfesional, fecha: date | None = None):
    fecha = fecha or timezone.localdate()
    return (Cita.objects.filter(profesional=profesional, fecha_hora__date=fecha)
            .select_related("expediente__persona", "servicio")
            .order_by("fecha_hora"))


def proximas_del_expediente(expediente, limite=5):
    return (Cita.objects.filter(
        expediente=expediente, estado__in=ESTADOS_ACTIVOS,
        fecha_hora__gte=timezone.now(),
    ).select_related("servicio", "profesional__usuario")
      .order_by("fecha_hora")[:limite])


def citas_para_recordatorio(horas_anticipacion: int,
                             tolerancia_minutos: int | None = None):
    """
    Devuelve citas cuya `fecha_hora` está a ~`horas_anticipacion` horas de ahora,
    dentro de una ventana de ±`tolerancia_minutos`.

    - En producción el task se programa cada 15 min con la tolerancia por
      defecto (15 min): cada cita cae en exactamente una ventana → sin
      duplicados y sin omisiones.
    - Para ejecuciones manuales o pruebas puede ampliarse la tolerancia.

    Estados considerados: RESERVADA y CONFIRMADA (fuente del recordatorio
    T-48h/T-24h, informe 5.2 M17).
    """
    tolerancia = tolerancia_minutos if tolerancia_minutos is not None \
        else TOLERANCIA_MINUTOS_DEFECTO
    ahora = timezone.now()
    centro = ahora + timedelta(hours=horas_anticipacion)
    inicio = centro - timedelta(minutes=tolerancia)
    fin = centro + timedelta(minutes=tolerancia)
    return Cita.objects.filter(
        fecha_hora__range=(inicio, fin),
        estado__in={Cita.Estado.RESERVADA, Cita.Estado.CONFIRMADA},
    ).select_related("expediente__persona", "servicio")
