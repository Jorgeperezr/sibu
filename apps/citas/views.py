"""Interfaz web del módulo de citas."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.expediente.services import resolver_por_cedula
from apps.usuarios.models import PerfilProfesional

from . import services
from .models import Cita
from .selectors import citas_del_dia


@login_required
def mi_agenda(request):
    """Agenda del día del profesional autenticado (o del elegido si tiene permisos)."""
    perfil = getattr(request.user, "perfil", None)
    fecha_str = request.GET.get("fecha")
    fecha = parse_date(fecha_str) if fecha_str else timezone.localdate()

    profesional_id = request.GET.get("profesional")
    if profesional_id and (request.user.is_staff or request.user.is_superuser):
        perfil = PerfilProfesional.objects.filter(pk=profesional_id).first()

    citas = citas_del_dia(perfil, fecha) if perfil else []
    return render(
        request,
        "citas/agenda_dia.html",
        {
            "citas": citas,
            "fecha": fecha,
            "perfil": perfil,
            "estados": Cita.Estado.choices,
        },
    )


@login_required
def reservar(request):
    """
    Formulario de reserva: busca por cédula, elige servicio/profesional/fecha
    y muestra los turnos disponibles (vía fetch al endpoint de disponibilidad).
    """
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
    """Endpoint ligero para el JS del formulario de reserva."""
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
    """Devuelve los profesionales asignados a un servicio."""
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
    cita = get_object_or_404(Cita, pk=pk)
    nuevo = request.POST.get("estado")
    try:
        services.cambiar_estado(cita, nuevo, usuario=request.user)
        messages.success(request, f"Cita actualizada a '{cita.get_estado_display()}'.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect(request.META.get("HTTP_REFERER", "citas:mi_agenda"))
