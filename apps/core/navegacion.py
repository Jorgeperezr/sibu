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
    #   ("servicio", "codigo")     -> tiene ese servicio asignado
    #   ("roles", {Rol, ...})      -> su rol_principal está en el conjunto
    #   ("siempre", None)          -> visible para cualquier autenticado
    #   ("tiene_servicio", None)   -> tiene AL MENOS un servicio, cualquiera
    #   ("permiso", "app.codigo")  -> tiene ese permiso de Django
    regla: tuple
    grupo: str  # para agrupar en la portada


# El orden aquí es el orden en que aparecen. Códigos de servicio = slugify del
# nombre del seed (p. ej. "Becas y Ayudas Económicas" -> "becas-y-ayudas-economicas").
MODULOS = [
    Modulo("Mi agenda", "citas:mi_agenda", ("siempre", None), "General"),
    # Dos entradas y no una: responden preguntas distintas. La agenda dice qué
    # hay HOY; el calendario, en qué días del mes hay algo, que era justo lo
    # que no se podía saber sin teclear fecha por fecha.
    Modulo("Calendario", "citas:calendario", ("siempre", None), "General"),
    Modulo("Medicina", "medicina:bandeja", ("servicio", "medicina"), "Salud"),
    Modulo("Enfermería", "enfermeria:bandeja", ("servicio", "enfermeria"), "Salud"),
    Modulo("Odontología", "odontologia:bandeja", ("servicio", "odontologia"), "Salud"),
    Modulo("Laboratorio", "laboratorio:bandeja", ("servicio", "laboratorio-clinico"), "Salud"),
    Modulo("Farmacia", "farmacia:mostrador", ("servicio", "farmacia"), "Salud"),
    Modulo("Psicología", "psicologia:bandeja", ("servicio", "psicologia"), "Psicopedagógica"),
    Modulo(
        "Psicopedagogía",
        "psicopedagogia:bandeja",
        ("servicio", "psicopedagogia"),
        "Psicopedagógica",
    ),
    # Trabajo Social era el único de los nueve servicios sin entrada: su
    # profesional iniciaba sesión y no tenía por dónde entrar a lo suyo.
    Modulo(
        "Trabajo Social",
        "trabajo_social:bandeja",
        ("servicio", "trabajo-social"),
        "Trabajo Social",
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
    # A diferencia del tablero de arriba —Dirección, agregados de TODA la
    # Unidad—, este lo genera cualquier profesional sobre su propio servicio:
    # es el mismo contenido que ya ve atención por atención.
    Modulo("Informe estadístico", "reportes:informe_servicio", ("tiene_servicio", None), "Gestión"),
    # El asistente de carga existía desde el Sprint 2 sin ninguna entrada de
    # menú: se llegaba escribiendo la URL a mano. `padron` es la puerta —desde
    # ahí se cargan archivos, se descarga la plantilla y se ve lo cargado—.
    # Por permiso y no por rol: la cuenta con la que se prueba el sistema lleva
    # rol PROFESIONAL a propósito —con rol de administrador el RBAC le negaría
    # el contenido clínico— pero sí tiene el permiso de carga. Es la misma
    # regla que aplica la vista, para que el menú no ofrezca un enlace que
    # luego responde 403, ni lo esconda a quien sí puede entrar.
    Modulo(
        "Base institucional",
        "academico:padron",
        ("permiso", "academico.add_cargainstitucional"),
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
    if tipo == "tiene_servicio":
        return bool(servicios_ids)
    if tipo == "permiso":
        return user.has_perm(dato)
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


@dataclass(frozen=True)
class AccionExpediente:
    """Algo que este usuario puede abrir o iniciar sobre un expediente."""

    etiqueta: str
    url_name: str  # recibe el id del expediente como único argumento
    regla: tuple  # mismo formato que Modulo.regla
    icono: str = ""
    variante: str = "outline-primary"


# Qué se puede iniciar desde un expediente. Igual que MODULOS, la visibilidad
# sale del RBAC: no hay una lista paralela de botones que se desincronice del
# 403 que daría la vista.
ACCIONES_EXPEDIENTE = [
    AccionExpediente("Triaje", "enfermeria:triaje", ("servicio", "enfermeria"), "clipboard-pulse"),
    AccionExpediente(
        "Consulta médica", "medicina:iniciar", ("servicio", "medicina"), "stethoscope"
    ),
    AccionExpediente(
        "Consulta odontológica", "odontologia:iniciar", ("servicio", "odontologia"), "emoji-smile"
    ),
    AccionExpediente(
        "Proceso psicológico", "psicologia:iniciar", ("servicio", "psicologia"), "chat-heart"
    ),
    AccionExpediente(
        "Ficha psicopedagógica",
        "psicopedagogia:iniciar",
        ("servicio", "psicopedagogia"),
        "book",
    ),
    AccionExpediente(
        "Ficha socioeconómica",
        "trabajo_social:ficha",
        ("servicio", "trabajo-social"),
        "house-heart",
    ),
    AccionExpediente(
        "Trazabilidad de derivaciones",
        "derivaciones:trazabilidad",
        ("siempre", None),
        "diagram-3",
        "outline-secondary",
    ),
]


def acciones_expediente(user):
    """Acciones que este usuario puede ejecutar sobre un expediente, en orden."""
    if not user.is_authenticated or getattr(user, "rol_principal", None) == Rol.USUARIO_FINAL:
        return []

    from apps.core.models import Servicio
    from apps.usuarios.rbac import servicios_del_usuario

    servicios_ids = servicios_del_usuario(user)
    codigos_por_id = dict(Servicio.objects.values_list("id", "codigo"))
    return [a for a in ACCIONES_EXPEDIENTE if _ve_modulo(user, a, servicios_ids, codigos_por_id)]


def modulos_por_grupo(user):
    """
    Los módulos visibles, agrupados y en el orden en que aparecen.

    La barra lateral crece por grupos: añadir un módulo es una fila más dentro
    del suyo, no un enlace que estrecha una barra horizontal ya llena. El campo
    `grupo` del dataclass existía desde el Sprint 12 sin usarse para esto.

    Devuelve [(grupo, [módulos]), ...] en vez de un dict para que el orden sea
    el de `MODULOS` y la plantilla no tenga que ordenar nada.
    """
    grupos: list[tuple[str, list]] = []
    indice: dict[str, list] = {}
    for modulo in modulos_visibles(user):
        if modulo.grupo not in indice:
            indice[modulo.grupo] = []
            grupos.append((modulo.grupo, indice[modulo.grupo]))
        indice[modulo.grupo].append(modulo)
    return grupos


def navegacion(request):
    """Context processor: expone la navegación en todas las plantillas."""
    return {
        "nav_modulos": modulos_visibles(request.user),
        "nav_grupos": modulos_por_grupo(request.user),
    }


def entorno(request):
    """
    Expone si esto es un entorno de desarrollo.

    Sirve para que ciertas pantallas den una pista que en el servidor real
    sería una filtración: la de inicio de sesión, por ejemplo, puede recordar
    que las credenciales se consultan con `make cuentas`.

    Se lee de `settings.DEBUG` y no de `django.template.context_processors.debug`,
    que solo define `debug` cuando la IP del cliente está en `INTERNAL_IPS`: en
    Codespaces la petición llega desde el reenvío de puertos y no lo está, así
    que aquella variable saldría vacía justo donde hace falta.
    """
    from django.conf import settings

    return {"es_desarrollo": bool(settings.DEBUG)}
