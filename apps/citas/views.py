"""
Interfaz web del módulo de citas.

Una cita se toca solo desde su propio servicio. `cambiar_estado_web` no lo
comprobaba: cualquier usuario autenticado cancelaba o marcaba como atendida
cualquier cita conociendo su id, incluida una de Psicología.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.expediente.services import resolver_por_cedula
from apps.usuarios import rbac
from apps.usuarios.models import PerfilProfesional
from apps.usuarios.rbac import servicios_del_usuario

from . import services
from .models import Cita
from .selectors import citas_del_dia


def _cita_del_usuario(user, pk) -> Cita:
    """
    La cita, si pertenece a un servicio del usuario; si no, 403.

    Se admite a cualquier profesional del servicio, no solo al titular de la
    agenda: un compañero cubre la consulta y necesita marcar la llegada o
    cancelar. Fuera del servicio, nadie.
    """
    cita = get_object_or_404(Cita.objects.select_related("servicio", "expediente__persona"), pk=pk)
    if cita.servicio_id not in servicios_del_usuario(user):
        raise PermissionDenied("Esta cita pertenece a otro servicio.")
    return cita


def _volver(request):
    """
    Vuelve a la página de origen, comprobándola.

    `HTTP_REFERER` es una cabecera: redirigir a ella sin validar convierte
    cualquiera de estas vistas en un salto a un sitio externo.
    """
    destino = request.META.get("HTTP_REFERER", "")
    if destino and url_has_allowed_host_and_scheme(
        destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(destino)
    return redirect("citas:mi_agenda")


def _solo_personal(request) -> None:
    """
    Estas pantallas son de trabajo: reservan, buscan personas y listan agendas
    con nombres de pacientes. `@login_required` solo pregunta si hay sesión,
    nunca de quién; es el mismo descuido que el Sprint 7b corrigió en nueve
    vistas. El estudiante tiene el portal, que aísla por identidad.
    """
    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("No tiene permisos para gestionar citas.")


@login_required
def mi_agenda(request):
    """
    Agenda del día del profesional autenticado (o del elegido si tiene permisos).

    Un estudiante la abría y salía vacía —no tiene perfil—, que es la clase de
    protección que deja de funcionar en cuanto alguien le asigna uno. La
    pantalla lista nombres de pacientes y motivos: se pide ser personal.
    """
    _solo_personal(request)
    perfil = getattr(request.user, "perfil", None)
    fecha_str = request.GET.get("fecha")
    fecha = parse_date(fecha_str) if fecha_str else timezone.localdate()

    # Ver la agenda de otro profesional exige compartir servicio con él. Antes
    # bastaba `is_staff`, una bandera del panel de administración de Django que
    # no dice nada sobre el servicio: con ella se leía la agenda de Psicología,
    # que lista los nombres de los pacientes y el motivo de cada cita.
    profesional_id = request.GET.get("profesional")
    if profesional_id:
        mis_servicios = servicios_del_usuario(request.user)
        perfil = (
            PerfilProfesional.objects.filter(pk=profesional_id, servicios__in=mis_servicios).first()
            if mis_servicios
            else None
        )
        if perfil is None:
            raise PermissionDenied("Ese profesional no comparte servicio con usted.")

    citas = citas_del_dia(perfil, fecha) if perfil else []
    return render(
        request,
        "citas/agenda_dia.html",
        {
            "citas": citas,
            "fecha": fecha,
            "perfil": perfil,
            "estados": Cita.Estado.choices,
            # Reprogramar y cancelar solo tienen sentido antes de atender; el
            # servicio lo valida igual, pero un botón que siempre falla molesta.
            "reprogramables": {Cita.Estado.RESERVADA, Cita.Estado.CONFIRMADA},
        },
    )


@login_required
def reservar(request):
    """
    Formulario de reserva: busca por cédula, elige servicio/profesional/fecha
    y muestra los turnos disponibles (vía fetch al endpoint de disponibilidad).

    Llevaba solo `@login_required`: un estudiante reservaba para cualquier
    expediente con cualquier profesional, Psicología incluida.
    """
    _solo_personal(request)
    contexto = {
        "servicios": Servicio.objects.filter(activo=True).select_related("seccion"),
    }
    if request.method == "POST":
        try:
            expediente = Expediente.objects.get(pk=request.POST["expediente"])
            servicio = Servicio.objects.get(pk=request.POST["servicio"])
            profesional = PerfilProfesional.objects.get(pk=request.POST["profesional"])
            fecha_hora = parse_datetime(request.POST["fecha_hora"])
            if fecha_hora is not None and timezone.is_naive(fecha_hora):
                fecha_hora = timezone.make_aware(fecha_hora, timezone.get_current_timezone())
            cita = services.reservar_cita(
                expediente=expediente,
                servicio=servicio,
                profesional=profesional,
                fecha_hora=fecha_hora,
                motivo=request.POST.get("motivo", ""),
                usuario=request.user,
            )
            messages.success(request, f"Cita reservada para {cita.fecha_hora:%d/%m/%Y %H:%M}.")
            return redirect("citas:mi_agenda")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        except (Expediente.DoesNotExist, Servicio.DoesNotExist, PerfilProfesional.DoesNotExist):
            messages.error(request, "Datos incompletos o inválidos.")
    return render(request, "citas/reservar.html", contexto)


@login_required
def buscar_persona_json(request):
    """
    Endpoint ligero para el JS del formulario de reserva.

    Tercera puerta a `resolver_por_cedula`, después de la vista `buscar` y de
    la API. No solo devuelve los datos institucionales de quien sea: esa
    llamada CREA la persona y su expediente si no existían.
    """
    _solo_personal(request)
    cedula = request.GET.get("cedula", "").strip()
    if not cedula:
        return JsonResponse({"error": "cedula requerida"}, status=400)
    resultado = resolver_por_cedula(cedula, usuario=request.user)
    if not resultado:
        return JsonResponse({"encontrado": False})
    persona = resultado["persona"]
    exp = resultado["expediente"]
    return JsonResponse(
        {
            "encontrado": True,
            "expediente_id": exp.id if exp else None,
            "nombre": persona.nombre_completo,
            "vinculo": persona.get_tipo_vinculo_display(),
        }
    )


@login_required
def profesionales_json(request):
    """
    Devuelve los profesionales asignados a un servicio.

    Alimenta el formulario de reserva, así que se cierra con él: quién atiende
    en cada servicio es directorio interno.
    """
    _solo_personal(request)
    servicio_id = request.GET.get("servicio")
    if not servicio_id:
        return JsonResponse({"profesionales": []})
    profesionales = (
        PerfilProfesional.objects.filter(servicios__id=servicio_id)
        .select_related("usuario")
        .distinct()
    )
    return JsonResponse(
        {
            "profesionales": [
                {"id": p.id, "nombre": p.usuario.get_full_name() or p.usuario.username}
                for p in profesionales
            ]
        }
    )


@login_required
def cambiar_estado_web(request, pk):
    """Cambio de estado desde la agenda (POST simple)."""
    cita = _cita_del_usuario(request.user, pk)
    nuevo = request.POST.get("estado")
    try:
        services.cambiar_estado(cita, nuevo, usuario=request.user)
        messages.success(request, f"Cita actualizada a '{cita.get_estado_display()}'.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return _volver(request)


@login_required
def cancelar(request, pk):
    """
    Cancela una cita con motivo escrito.

    `services.cancelar` existía desde el Sprint 3 sin pantalla que llegara a
    él: cancelar exigía el shell. El motivo se exige aquí porque el servicio
    lo admite vacío y una cancelación sin causa no se puede explicar después.
    """
    cita = _cita_del_usuario(request.user, pk)
    motivo = request.POST.get("motivo", "").strip()
    if not motivo:
        messages.error(request, "Indique el motivo de la cancelación.")
        return _volver(request)
    try:
        services.cancelar(cita, motivo, usuario=request.user)
        messages.warning(request, "Cita cancelada.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return _volver(request)


@login_required
def reprogramar(request, pk):
    """
    Mueve la cita a otra hora. La original queda como REPROGRAMADA y la nueva
    enlaza con ella por `cita_origen`, así que el historial no se pierde.
    """
    cita = _cita_del_usuario(request.user, pk)
    fecha_hora = parse_datetime(request.POST.get("fecha_hora", "") or "")
    if fecha_hora is None:
        messages.error(request, "La nueva fecha y hora no son válidas.")
        return _volver(request)
    if timezone.is_naive(fecha_hora):
        fecha_hora = timezone.make_aware(fecha_hora, timezone.get_current_timezone())
    try:
        nueva = services.reprogramar(
            cita,
            fecha_hora,
            usuario=request.user,
            motivo_reprogramacion=request.POST.get("motivo", "").strip(),
        )
        messages.success(
            request, f"Reprogramada para {timezone.localtime(nueva.fecha_hora):%d/%m/%Y %H:%M}."
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return _volver(request)
