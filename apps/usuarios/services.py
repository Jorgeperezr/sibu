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
CAMPOS_CUENTA = ("first_name", "last_name", "cedula", "telefono", "email", "fecha_nacimiento")
CAMPOS_PERFIL = ("titulo", "registro_profesional", "denominacion_cargo")
# `fecha_nacimiento` llega como texto ISO ("YYYY-MM-DD") de un <input
# type="date">, o cadena vacía: no se le aplica `.strip()` como al resto.
CAMPOS_FECHA = ("fecha_nacimiento",)


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

    fecha_nacimiento = datos.get("fecha_nacimiento", "")
    if fecha_nacimiento:
        from datetime import date

        from django.utils.dateparse import parse_date

        fecha = parse_date(fecha_nacimiento)
        if fecha is None:
            raise ValidationError("La fecha de nacimiento no es válida.")
        if fecha > date.today():
            raise ValidationError("La fecha de nacimiento no puede ser futura.")

    with transaction.atomic():
        for campo in CAMPOS_CUENTA:
            if campo not in datos:
                continue
            if campo == "cedula":
                # Única y admite NULL: dejarla en cadena vacía haría chocar a
                # la segunda cuenta que se guardara sin cédula.
                valor = cedula or None
            elif campo in CAMPOS_FECHA:
                # DateField.to_python la parsea al guardar; cadena vacía -> None.
                valor = datos[campo] or None
            else:
                valor = datos[campo].strip()
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


# ============================================================
# Actividades esenciales del manual de puestos
# ============================================================


def agregar_actividad(perfil, descripcion: str, actividad_superior=None):
    """
    Agrega una actividad esencial al final de su lista.

    Sin `actividad_superior` es una fila de primer nivel (una de las diez a
    trece del manual). Con ella, es una sub-actividad de las que suelen
    acumularse bajo la última —"las demás que asigne el jefe inmediato"—; se
    numera dentro de esa lista propia, no en la general.

    El siguiente `orden` se calcula, no se recibe: quien agrega una actividad
    no tiene por qué saber cuántas hay ya, y dejarlo a su cargo abriría la
    puerta a huecos o choques de numeración.
    """
    from django.core.exceptions import ValidationError

    from .models import ActividadEsencial

    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise ValidationError("La actividad necesita una descripción.")

    if actividad_superior is not None and actividad_superior.perfil_id != perfil.pk:
        raise ValidationError("Esa actividad superior no pertenece a este perfil.")

    hermanas = ActividadEsencial.objects.filter(
        perfil=perfil, actividad_superior=actividad_superior
    )
    siguiente_orden = (hermanas.order_by("-orden").values_list("orden", flat=True).first() or 0) + 1

    return ActividadEsencial.objects.create(
        perfil=perfil,
        actividad_superior=actividad_superior,
        orden=siguiente_orden,
        descripcion=descripcion,
    )


def eliminar_actividad(actividad):
    """
    Quita una actividad esencial. Si tenía sub-actividades, se van con ella
    —`on_delete=CASCADE`—: no puede quedar una sub-actividad huérfana de la
    fila del manual que la contiene.
    """
    actividad.delete()
