"""
Menú de navegación derivado de lo que cada usuario puede ver.

Un único mapa de módulos vive aquí; la cabecera y la portada lo consumen. No
hay listas paralelas que se desincronicen: si mañana se añade un módulo, se
añade una fila y aparece en los dos sitios a la vez.

La visibilidad reutiliza el RBAC existente (`servicios_del_usuario`,
`rol_principal`), no una regla nueva: el menú no debe poder mostrar un enlace a
algo que la vista luego niega con 403, ni ocultar algo a lo que sí se tiene
acceso.
"""

from dataclasses import dataclass

from apps.usuarios.models import Rol


@dataclass(frozen=True)
class Modulo:
    etiqueta: str
    url_name: str  # nombre de URL con namespace; None si la ruta pide un id
    # Cómo se decide si este usuario lo ve. Una de:
    #   ("servicio", "codigo")   -> tiene ese servicio asignado
    #   ("roles", {Rol, ...})    -> su rol_principal está en el conjunto
    #   ("siempre", None)        -> visible para cualquier autenticado
    regla: tuple
    grupo: str  # para agrupar en la portada


# El orden aquí es el orden en que aparecen. Códigos de servicio = slugify del
# nombre del seed (p. ej. "Becas y Ayudas Económicas" -> "becas-y-ayudas-economicas").
MODULOS = [
    Modulo("Mi agenda", "citas:mi_agenda", ("siempre", None), "General"),
    Modulo("Laboratorio", "laboratorio:bandeja", ("servicio", "laboratorio-clinico"), "Salud"),
    Modulo("Farmacia", "farmacia:mostrador", ("servicio", "farmacia"), "Salud"),
    Modulo("Psicología", "psicologia:bandeja", ("servicio", "psicologia"), "Psicopedagógica"),
    Modulo(
        "Psicopedagogía",
        "psicopedagogia:bandeja",
        ("servicio", "psicopedagogia"),
        "Psicopedagógica",
    ),
    Modulo("Derivaciones", "derivaciones:bandeja", ("siempre", None), "General"),
    Modulo("Becas", "becas:bandeja", ("servicio", "becas-y-ayudas-economicas"), "Becas"),
    Modulo("Talleres", "talleres:bandeja", ("siempre", None), "General"),
    Modulo(
        "Reportes",
        "reportes:tablero",
        ("roles", {Rol.ADMIN_GENERAL, Rol.DIRECTOR, Rol.COORDINADOR}),
        "Gestión",
    ),
]

# Rutas de módulos que solo se abren desde un expediente/atención concreta. No
# van al menú como enlace directo (piden un id), pero la búsqueda de
# expedientes es su puerta de entrada, así que esa sí se ofrece.
BUSQUEDA_EXPEDIENTES = Modulo("Expedientes", "expediente:buscar", ("siempre", None), "General")


def _ve_modulo(user, modulo: Modulo, servicios_ids: set, codigos_por_id: dict) -> bool:
    tipo, dato = modulo.regla
    if tipo == "siempre":
        return True
    if tipo == "roles":
        return getattr(user, "rol_principal", None) in dato
    if tipo == "servicio":
        # Admin ve todos los enlaces para poder navegar; el acceso fino al
        # contenido lo sigue resolviendo cada vista.
        if getattr(user, "rol_principal", None) == Rol.ADMIN_GENERAL:
            return True
        codigos = {codigos_por_id.get(sid) for sid in servicios_ids}
        return dato in codigos
    return False


def modulos_visibles(user):
    """Lista de módulos que este usuario puede ver, en orden."""
    if not user.is_authenticated:
        return []

    # Un usuario del portal no navega los módulos internos: su sitio es /portal/.
    if getattr(user, "rol_principal", None) == Rol.USUARIO_FINAL:
        return [Modulo("Mi portal", "portal:inicio", ("siempre", None), "General")]

    from apps.core.models import Servicio
    from apps.usuarios.rbac import servicios_del_usuario

    servicios_ids = servicios_del_usuario(user)
    codigos_por_id = dict(Servicio.objects.values_list("id", "codigo"))

    visibles = [BUSQUEDA_EXPEDIENTES]
    visibles += [m for m in MODULOS if _ve_modulo(user, m, servicios_ids, codigos_por_id)]
    return visibles


def navegacion(request):
    """Context processor: expone `nav_modulos` en todas las plantillas."""
    return {"nav_modulos": modulos_visibles(request.user)}
