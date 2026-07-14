"""Servicios de usuarios: acceso de emergencia (break the glass) y auditoría RBAC."""
from __future__ import annotations

from apps.auditoria.models import LogAuditoria


def registrar_break_glass(user, expediente_id, motivo, ip=None, user_agent=""):
    """
    Registra un acceso de emergencia justificado (informe 10.2, 14.5).
    Deja constancia destacada en la auditoría; la notificación al Director la
    dispara una señal a partir de este log.
    """
    return LogAuditoria.objects.create(
        usuario=user,
        rol_activo=getattr(user, "rol_principal", ""),
        accion=LogAuditoria.Accion.BREAK_GLASS,
        modulo="expediente",
        entidad="Expediente",
        entidad_id=str(expediente_id),
        expediente_id=expediente_id,
        detalle={"motivo": motivo},
        ip=ip,
        user_agent=user_agent[:255] if user_agent else "",
    )
