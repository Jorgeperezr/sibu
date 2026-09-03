"""Consultas de lectura del expediente (con filtrado RBAC)."""

from __future__ import annotations

from apps.usuarios.rbac import atenciones_visibles, servicios_del_usuario

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
    atenciones = list(timeline(expediente, usuario, break_glass))
    # De qué atenciones puede derivar este usuario. Es la misma regla que aplica
    # `derivaciones.views.derivar` (solo desde un servicio propio): calcularla
    # aquí evita ofrecer un botón que respondería 403. Ver una atención por
    # break-glass no habilita derivar desde ella.
    mis_servicios = servicios_del_usuario(usuario)
    for atencion in atenciones:
        atencion.puede_derivar = atencion.servicio_id in mis_servicios
    return {
        "expediente": expediente,
        "persona": expediente.persona,
        "alertas": list(alertas_activas(expediente)),
        "atenciones": atenciones,
        "total_atenciones": len(atenciones),
    }
