"""
Interfaz web del expediente: búsqueda por cédula y ficha del expediente.

La búsqueda por cédula (informe 7.5) es el punto de entrada de todo el trabajo
clínico: resuelve la persona contra la base institucional, muestra la tarjeta de
verificación con semáforo de matrícula y enlaza al expediente único.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.navegacion import acciones_expediente
from apps.usuarios import rbac

from . import campos as campos_alta
from .models import AlertaClinica, Expediente, Persona
from .selectors import MINIMO_TEXTO, buscar_personas, resumen_expediente
from .services import (
    MAXIMO_POR_LOTE,
    registrar_alerta,
    registrar_lote_de_cedulas,
    registrar_persona,
    resolver_por_cedula,
)

# Qué acepta el alta. Explícito, y no el POST entero volcado en el modelo: un
# campo de más aquí es un dato que nadie validó. Vive en `campos.py` junto con
# los rótulos y los grupos JSON.
CAMPOS_ALTA = campos_alta.CAMPOS_PERSONA + campos_alta.CAMPOS_EXPEDIENTE


@login_required
def buscar(request):
    """
    Busca por cédula exacta o por nombre y ofrece abrir el expediente.

    Solo la cédula resuelve contra la fuente institucional, porque esa consulta
    CREA la persona y su expediente si no existían. La búsqueda por nombre no
    escribe nada: lee el padrón local y ya.

    Ninguna de las dos revela qué servicio atiende a la persona; eso delataría
    un paso por un servicio confidencial. El contenido clínico sigue filtrándose
    en la línea de tiempo del expediente.
    """
    # `nuevo` y `detalle` ya exigían este permiso; `buscar` no, y era la puerta
    # de las tres: un estudiante consultaba cualquier cédula, veía nombre,
    # vínculo, facultad, carrera y estado de matrícula, y de paso la consulta
    # le abría un expediente a esa persona.
    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("No tiene permisos para consultar expedientes.")

    contexto = {}
    nombre = (request.GET.get("nombre") or "").strip()
    if nombre:
        contexto["nombre"] = nombre
        contexto["resultados"] = buscar_personas(nombre)
        if len(nombre) < MINIMO_TEXTO:
            messages.info(request, f"Escriba al menos {MINIMO_TEXTO} letras para buscar.")
        elif not contexto["resultados"]:
            messages.warning(request, f"Ninguna persona registrada coincide con «{nombre}».")

    cedula = (request.GET.get("cedula") or "").strip()
    if cedula:
        resultado = resolver_por_cedula(cedula, usuario=request.user)
        if resultado is None:
            messages.warning(
                request,
                f"La cédula {cedula} no está en la base institucional. "
                "Puede registrarla como persona externa.",
            )
        else:
            inst = resultado["institucional"] or {}
            # Semáforo de vinculación (informe 7.5)
            estado = (inst.get("estado") or "").lower()
            if "matricul" in estado:
                semaforo = "success"
            elif inst:
                semaforo = "warning"
            else:
                semaforo = "danger"
            contexto.update(
                {
                    "persona": resultado["persona"],
                    "expediente": resultado["expediente"],
                    "institucional": inst,
                    "semaforo": semaforo,
                }
            )
        contexto["cedula"] = cedula
    return render(request, "expediente/buscar.html", contexto)


def _datos_institucionales(cedula: str) -> dict:
    """Lo que la fuente académica sepa de esa cédula, para precargar el alta."""
    from apps.academico.providers import get_provider
    from apps.academico.validators import normalizar_cedula

    ficha = get_provider().consultar_persona(normalizar_cedula(cedula)) or {}
    if not ficha:
        return {}
    return {
        "nombres": ficha.get("nombres", ""),
        "apellidos": ficha.get("apellidos", ""),
        "correo_institucional": ficha.get("email_institucional", ""),
        "tipo_vinculo": ficha.get("tipo_vinculo", ""),
        "prellenado": True,
    }


@login_required
def nuevo(request):
    """
    Alta de una persona y apertura de su expediente.

    La búsqueda ofrecía "puede registrarla como persona externa" sin dar por
    dónde: sin esta pantalla, dar de alta a un paciente exigía el shell, y todos
    los módulos parten de un expediente existente.
    """
    if not rbac.puede_ver_expediente(request.user):
        messages.error(request, "No tiene permisos para registrar expedientes.")
        return redirect("expediente:buscar")

    datos = {"cedula": (request.GET.get("cedula") or "").strip()}
    # Si la cédula ya consta en la fuente institucional, sus datos se traen
    # solos: hacer teclear de nuevo lo que la Universidad ya sabe invita a
    # escribirlo distinto y a partir en dos la identidad de la persona.
    if datos["cedula"] and request.method == "GET":
        datos.update(_datos_institucionales(datos["cedula"]))

    if request.method == "POST":
        datos = {campo: (request.POST.get(campo) or "").strip() for campo in CAMPOS_ALTA}
        # Las casillas de los grupos (procedencia, residencia, contacto) llegan
        # como `prefijo-clave`; el servicio las reparte a su JSON.
        for clave, valor in request.POST.items():
            if "-" in clave and clave.split("-", 1)[0] in {
                p for p, _a, _t in campos_alta.GRUPOS_JSON
            }:
                datos[clave] = valor.strip()
        try:
            expediente = registrar_persona(datos, usuario=request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                f"Expediente {expediente.numero_expediente} abierto para "
                f"{expediente.persona.nombre_completo}.",
            )
            return redirect("expediente:detalle", pk=expediente.pk)

    return render(
        request,
        "expediente/nuevo.html",
        {
            "datos": datos,
            "vinculos": Persona.TipoVinculo.choices,
            # Con los valores de vuelta: si el alta se rechaza —una cédula que
            # no pasa el módulo 10— el formulario se vuelve a pintar, y sin
            # esto se perdería todo lo tecleado en estos grupos.
            "grupos": campos_alta.grupos_para_formulario(datos),
        },
    )


@login_required
def detalle(request, pk):
    """Ficha del expediente: encabezado, alertas y línea de tiempo (con RBAC)."""
    if not rbac.puede_ver_expediente(request.user):
        messages.error(request, "No tiene permisos para ver expedientes.")
        return redirect("expediente:buscar")

    expediente = get_object_or_404(Expediente, pk=pk)
    break_glass = request.GET.get("break_glass") == "1"
    contexto = resumen_expediente(expediente, request.user, break_glass=break_glass)
    contexto["break_glass"] = break_glass
    # Sin esto el expediente era una pantalla de solo lectura: la ficha se veía,
    # pero abrir una consulta exigía teclear la URL a mano.
    contexto["acciones"] = acciones_expediente(request.user)
    contexto["tipos_alerta"] = AlertaClinica.Tipo.choices
    return render(request, "expediente/detalle.html", contexto)


@login_required
def alertas(request, pk):
    """
    Registra una alerta clínica sobre el expediente.

    Mismo criterio de acceso que `detalle`: quien puede abrir el expediente
    puede marcar una bandera sobre él. `AlertaClinica` es visible en todo el
    expediente por diseño, así que esto no abre ninguna rendija nueva en el
    sello de Psicología.
    """
    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("No tiene permisos para registrar alertas.")

    expediente = get_object_or_404(Expediente, pk=pk)
    try:
        registrar_alerta(
            expediente,
            request.POST.get("tipo", ""),
            request.POST.get("descripcion", ""),
            usuario=request.user,
        )
        messages.success(request, "Alerta registrada.")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect("expediente:detalle", pk=expediente.pk)


@login_required
def alta_masiva(request):
    """
    Abre expedientes para varias cédulas de una vez.

    Hasta ahora la búsqueda resolvía una cédula por vez, y preparar una jornada
    —una brigada de salud, un taller, la lista de un curso— obligaba a repetir
    la misma pantalla decenas de veces.

    Exige el mismo permiso que la búsqueda, y por el mismo motivo: esto
    consulta el padrón institucional y abre expedientes. La versión de una en
    una ya estaba abierta a cualquier autenticado y hubo que cerrarla; abrir
    aquí una puerta de doscientas a la vez habría sido peor.
    """
    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("No tiene permisos para registrar expedientes.")

    contexto = {"maximo": MAXIMO_POR_LOTE}
    if request.method == "POST":
        texto = request.POST.get("cedulas", "")
        contexto["cedulas"] = texto
        try:
            contexto["resultado"] = registrar_lote_de_cedulas(texto, usuario=request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            resumen = contexto["resultado"]["resumen"]
            messages.success(
                request,
                f"{resumen['abierto']} expediente(s) abierto(s), "
                f"{resumen['existente']} ya existía(n), "
                f"{resumen['invalida']} cédula(s) inválida(s), "
                f"{resumen['desconocida']} sin datos institucionales.",
            )
    return render(request, "expediente/alta_masiva.html", contexto)


def _ficha_institucional(cedula: str) -> dict:
    """La matrícula tal como la conoce el proveedor académico, o vacío."""
    from apps.academico.providers import get_provider
    from apps.academico.validators import normalizar_cedula

    return get_provider().consultar_persona(normalizar_cedula(cedula)) or {}


@login_required
def datos(request, pk):
    """
    Los datos de la persona vistos desde MI servicio, y su ajuste.

    La base institucional es la foto del día de la matrícula. Un servicio
    encuentra otra realidad —la ficha dice que no hay embarazo y en consulta se
    registra uno— y necesita anotarlo sin reescribir esa base, que es la fuente
    para todo el sistema.

    Se muestran los dos valores, el institucional y el del servicio, porque un
    dato corregido sin poder ver contra qué se corrigió no se puede revisar.
    """
    from apps.core.models import Servicio

    from .selectors import valores_efectivos
    from .services import NO_AJUSTABLES, quitar_ajuste, registrar_ajuste

    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("No tiene permisos para ver expedientes.")

    expediente = get_object_or_404(Expediente.objects.select_related("persona"), pk=pk)

    # Solo se ajusta desde un servicio propio: el ajuste vale dentro de ese
    # servicio, así que ajustarlo desde fuera no significaría nada.
    mis_servicios = Servicio.objects.filter(pk__in=rbac.servicios_del_usuario(request.user))
    elegido = request.GET.get("servicio") or request.POST.get("servicio") or ""
    servicio = mis_servicios.filter(codigo=elegido).first() or mis_servicios.first()

    if request.method == "POST":
        if servicio is None:
            raise PermissionDenied("Su usuario no tiene ningún servicio asignado.")
        try:
            if request.POST.get("accion") == "quitar":
                quitar_ajuste(
                    expediente, servicio, request.POST.get("variable", ""), usuario=request.user
                )
                messages.success(request, "Ajuste retirado; vuelve el dato de matrícula.")
            else:
                registrar_ajuste(
                    expediente,
                    servicio,
                    request.POST.get("variable", ""),
                    request.POST.get("valor", ""),
                    usuario=request.user,
                    nota=request.POST.get("nota", ""),
                )
                messages.success(request, f"Dato ajustado para {servicio.nombre}.")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(f"{request.path}?servicio={servicio.codigo}")

    return render(
        request,
        "expediente/datos.html",
        {
            "expediente": expediente,
            "persona": expediente.persona,
            "servicio": servicio,
            "mis_servicios": mis_servicios,
            "filas": valores_efectivos(expediente, servicio),
            "no_ajustables": NO_AJUSTABLES,
            # Del proveedor y no de `_datos_institucionales`, que solo devuelve
            # lo que hace falta para prellenar un alta: aquí se quiere la
            # matrícula completa (facultad, carrera, ciclo, estado).
            "institucional": _ficha_institucional(expediente.persona.cedula),
        },
    )
