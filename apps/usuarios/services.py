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


# Lo que un profesional puede corregir de su propia ficha. Deliberadamente NO
# están aquí `servicios`, `seccion`, `rol_principal` ni `puede_firmar_digital`:
# de esos depende el RBAC, y quien los editara se ampliaría el acceso a sí
# mismo. Los asigna quien administra, desde el panel.
CAMPOS_CUENTA = ("first_name", "last_name", "cedula", "telefono", "email")
CAMPOS_PERFIL = ("titulo", "registro_profesional")


def actualizar_mi_perfil(usuario, datos: dict):
    """
    Actualiza los datos propios del profesional y devuelve su perfil.

    La cédula se normaliza y se valida con el módulo 10: es la que identifica
    al firmante ante FirmaEC, así que una mal digitada aquí bloquearía la firma
    más tarde y en otro sitio.

    Se valida TODO antes de escribir nada. `ATOMIC_REQUESTS` envuelve la
    petición entera: registrar el rechazo y luego lanzar ValidationError
    revertiría el propio registro, así que aquí no se audita lo rechazado.
    """
    from django.core.exceptions import ValidationError
    from django.db import transaction

    from apps.academico.validators import normalizar_cedula, validar_cedula_ecuatoriana
    from apps.auditoria.models import LogAuditoria

    from .models import PerfilProfesional, Usuario

    cedula = datos.get("cedula", "")
    if cedula:
        cedula = normalizar_cedula(cedula)
        if not validar_cedula_ecuatoriana(cedula):
            raise ValidationError(f"La cédula {cedula} no es válida (módulo 10).")
        # `Usuario` explícito, no `type(usuario)`: desde una vista llega un
        # SimpleLazyObject y `type(...)` devuelve la envoltura, que no tiene
        # manager. Con un objeto real —como en las pruebas del servicio— sí
        # funcionaba, así que el fallo solo salía en pantalla.
        ajena = (
            Usuario.objects.filter(cedula=cedula)
            .exclude(pk=usuario.pk)
            .values_list("username", flat=True)
            .first()
        )
        if ajena:
            raise ValidationError("Esa cédula ya está registrada en otra cuenta.")

    with transaction.atomic():
        for campo in CAMPOS_CUENTA:
            if campo not in datos:
                continue
            # `cedula` es única y admite NULL: dejarla en cadena vacía haría
            # chocar a la segunda cuenta que se guardara sin cédula.
            valor = (cedula or None) if campo == "cedula" else datos[campo].strip()
            setattr(usuario, campo, valor)
        usuario.save(update_fields=[c for c in CAMPOS_CUENTA if c in datos])

        perfil, _ = PerfilProfesional.objects.get_or_create(usuario=usuario)
        for campo in CAMPOS_PERFIL:
            if campo in datos:
                setattr(perfil, campo, datos[campo].strip())
        perfil.save(update_fields=[c for c in CAMPOS_PERFIL if c in datos] or None)

        LogAuditoria.objects.create(
            usuario=usuario,
            rol_activo=getattr(usuario, "rol_principal", ""),
            accion=LogAuditoria.Accion.UPDATE,
            modulo="usuarios",
            entidad="PerfilProfesional",
            entidad_id=str(perfil.pk),
            detalle={"campos": sorted(set(datos) & set(CAMPOS_CUENTA + CAMPOS_PERFIL))},
        )
    return perfil
