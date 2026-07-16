"""
Núcleo del control de acceso basado en roles (RBAC) — informe, sección 10.

Formaliza la matriz de permisos como reglas evaluables en tres capas
(informe 14.2): permiso de acción por rol, alcance por sección/servicio y
filtrado de expedientes. Las apps de servicio y la API consumen estas funciones
para no depender solo de la interfaz.

El acceso al detalle clínico de OTRO servicio/sección requiere "break the glass"
(acceso de emergencia justificado y auditado). El contenido de Psicología queda
excluido incluso de ese mecanismo salvo riesgo vital documentado.
"""

from __future__ import annotations

from apps.usuarios.models import Rol

# Servicios cuyo contenido clínico es de confidencialidad reforzada.
SERVICIOS_CONFIDENCIALES = {"psicologia"}

# Roles con visión agregada de toda la Unidad (sin detalle clínico por defecto).
ROLES_DIRECCION = {Rol.DIRECTOR, Rol.ADMIN_GENERAL}


def es_admin(user) -> bool:
    return getattr(user, "is_superuser", False) or user.rol_principal == Rol.ADMIN_GENERAL


def servicios_del_usuario(user):
    """IDs de servicios asignados al profesional (vacío si no tiene perfil)."""
    perfil = getattr(user, "perfil", None)
    if perfil is None:
        return set()
    return set(perfil.servicios.values_list("id", flat=True))


def seccion_del_usuario(user):
    perfil = getattr(user, "perfil", None)
    return getattr(perfil, "seccion_id", None)


def puede_ver_servicio(user, servicio) -> bool:
    """
    ¿Puede el usuario ver el contenido clínico de un servicio dado?
    - Admin: no (separación de funciones); accede solo con elevación registrada.
    - Profesional: sí, si el servicio está entre los suyos.
    - Coordinador: sí, para los servicios de su sección.
    - Director: agregados, no detalle (devuelve False aquí).
    """
    if user.rol_principal == Rol.PROFESIONAL:
        return getattr(servicio, "id", servicio) in servicios_del_usuario(user)
    if user.rol_principal == Rol.COORDINADOR:
        seccion = seccion_del_usuario(user)
        servicio_seccion = getattr(getattr(servicio, "seccion", None), "id", None)
        return seccion is not None and seccion == servicio_seccion
    return False


def puede_ver_atencion(user, atencion, break_glass: bool = False) -> bool:
    """Regla de acceso a una atención concreta del expediente."""
    servicio = atencion.servicio
    # El propio profesional que la realizó siempre puede verla.
    perfil = getattr(user, "perfil", None)
    if perfil is not None and atencion.profesional_id == perfil.pk:
        return True
    # Contenido confidencial (Psicología): solo el tratante, nunca break-the-glass.
    if servicio.codigo in SERVICIOS_CONFIDENCIALES:
        return False
    if puede_ver_servicio(user, servicio):
        return True
    # Acceso de emergencia justificado para el resto de servicios.
    return bool(break_glass) and user.rol_principal in {
        Rol.PROFESIONAL,
        Rol.COORDINADOR,
        Rol.DIRECTOR,
    }


def puede_ver_expediente(user, break_glass: bool = False) -> bool:
    """¿Puede el usuario abrir un expediente (encabezado demográfico)?"""
    return user.rol_principal in {
        Rol.PROFESIONAL,
        Rol.COORDINADOR,
        Rol.DIRECTOR,
        Rol.ADMINISTRATIVO,
        Rol.LABORATORIO,
        Rol.FARMACIA,
    } or es_admin(user)


def atenciones_visibles(user, queryset, break_glass: bool = False):
    """
    Filtra un queryset de Atencion según el rol (defensa en profundidad).
    Aplica la lógica de `puede_ver_atencion` a nivel de consulta cuando es posible.
    """
    from apps.usuarios.models import Rol as _Rol

    perfil = getattr(user, "perfil", None)
    if es_admin(user) and not break_glass:
        # El admin no ve contenido clínico por defecto.
        return queryset.none()

    if user.rol_principal == _Rol.PROFESIONAL:
        base = queryset.filter(servicio_id__in=servicios_del_usuario(user))
        if perfil is not None:
            base = base | queryset.filter(profesional_id=perfil.pk)
        return base.distinct()

    if user.rol_principal == _Rol.COORDINADOR:
        seccion = seccion_del_usuario(user)
        base = queryset.filter(servicio__seccion_id=seccion)
        # Nunca Psicología salvo que sea el tratante.
        return base.exclude(servicio__codigo__in=SERVICIOS_CONFIDENCIALES)

    if break_glass and user.rol_principal in {_Rol.DIRECTOR, _Rol.COORDINADOR, _Rol.PROFESIONAL}:
        return queryset.exclude(servicio__codigo__in=SERVICIOS_CONFIDENCIALES)

    return queryset.none()
