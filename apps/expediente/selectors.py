"""Consultas de lectura del expediente (con filtrado RBAC)."""

from __future__ import annotations

from apps.usuarios.rbac import atenciones_visibles

from .models import AlertaClinica, Atencion, Expediente


def timeline(expediente: Expediente, usuario, break_glass: bool = False):
    """
    Línea de tiempo consolidada de todas las atenciones del expediente,
    filtrada por lo que el rol del usuario puede ver (informe 5.2 RF-EXP-02).
    """
    base = (
        Atencion.objects.filter(expediente=expediente)
        .select_related("servicio", "profesional", "profesional__usuario")
        .order_by("-fecha_hora")
    )
    return atenciones_visibles(usuario, base, break_glass=break_glass)


def alertas_activas(expediente: Expediente):
    return AlertaClinica.objects.filter(expediente=expediente, activa=True)


def resumen_expediente(expediente: Expediente, usuario, break_glass: bool = False):
    """Encabezado + alertas + conteo de atenciones visibles para el usuario."""
    atenciones = timeline(expediente, usuario, break_glass)
    return {
        "expediente": expediente,
        "persona": expediente.persona,
        "alertas": list(alertas_activas(expediente)),
        "atenciones": atenciones,
        "total_atenciones": atenciones.count(),
    }
