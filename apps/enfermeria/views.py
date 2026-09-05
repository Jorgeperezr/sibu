"""Interfaz web de Enfermería: registro de triaje / signos vitales."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.usuarios.decorators import verificar_es_del_servicio

from .models import SignosVitales
from .services import signos_del_dia, triajes_del_dia


def _dec(valor):
    """Convierte a Decimal o None si viene vacío/invalido."""
    if not valor:
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None


def _int(valor):
    try:
        return int(valor) if valor else None
    except (TypeError, ValueError):
        return None


def _servicio():
    """El servicio de Enfermería, fuente única del criterio de acceso."""
    return get_object_or_404(Servicio, codigo="enfermeria")


@login_required
def bandeja(request):
    """Cola de trabajo de Enfermería: los triajes tomados hoy."""
    verificar_es_del_servicio(request.user, _servicio())
    return render(request, "enfermeria/bandeja.html", {"triajes": triajes_del_dia()})


@login_required
def triaje(request, expediente_id):
    """Registra signos vitales del expediente (triaje previo a Medicina)."""
    # Los signos vitales son contenido clínico: sin esto cualquier autenticado
    # los leía y los registraba sobre el expediente de cualquiera.
    verificar_es_del_servicio(request.user, _servicio())
    expediente = get_object_or_404(Expediente, pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        if perfil is None:
            messages.error(request, "Su usuario no tiene perfil profesional asignado.")
            return redirect("expediente:detalle", pk=expediente.id)
        SignosVitales.objects.create(
            expediente=expediente,
            temperatura=_dec(request.POST.get("temperatura")),
            fc=_int(request.POST.get("fc")),
            fr=_int(request.POST.get("fr")),
            pa_sistolica=_int(request.POST.get("pa_sistolica")),
            pa_diastolica=_int(request.POST.get("pa_diastolica")),
            sat_o2=_int(request.POST.get("sat_o2")),
            peso=_dec(request.POST.get("peso")),
            talla=_dec(request.POST.get("talla")),
            perimetro_abdominal=_int(request.POST.get("perimetro_abdominal")),
            glicemia_capilar=_int(request.POST.get("glicemia_capilar")),
            responsable=perfil,
        )
        messages.success(request, "Signos vitales registrados. Disponibles para Medicina.")
        return redirect("enfermeria:triaje", expediente_id=expediente.id)

    return render(
        request,
        "enfermeria/triaje.html",
        {
            "expediente": expediente,
            "persona": expediente.persona,
            "signos_hoy": signos_del_dia(expediente),
        },
    )
