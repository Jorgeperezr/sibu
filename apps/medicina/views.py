"""Interfaz web de Medicina: escritorio de consulta."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import CIE10, Servicio
from apps.enfermeria.services import ultimo_triaje
from apps.expediente.models import Atencion, Expediente
from apps.usuarios.decorators import verificar_acceso_atencion, verificar_es_del_servicio

from . import services
from .models import AtencionMedicina


@login_required
def bandeja(request):
    """
    Cola de trabajo de Medicina: las historias aún en borrador del servicio.

    Mismo criterio que el menú (`servicios_del_usuario`): quien ve el enlace
    entra y quien no lo ve recibe 403.
    """
    servicio = get_object_or_404(Servicio, codigo="medicina")
    verificar_es_del_servicio(request.user, servicio)

    historias = (
        AtencionMedicina.objects.filter(
            atencion__servicio=servicio, atencion__estado=Atencion.Estado.BORRADOR
        )
        .select_related("atencion__expediente__persona", "atencion__profesional__usuario")
        .order_by("-atencion__fecha_hora")
    )
    return render(request, "medicina/bandeja.html", {"historias": historias})


@login_required
def iniciar_consulta(request, expediente_id):
    """Crea la HC médica en borrador y redirige al escritorio de consulta."""
    expediente = get_object_or_404(Expediente, pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        messages.error(request, "Su usuario no tiene perfil profesional asignado.")
        return redirect("expediente:detalle", pk=expediente.id)
    try:
        hc = services.crear_atencion_medicina(
            expediente=expediente,
            profesional=perfil,
            motivo=request.POST.get("motivo", ""),
            usuario=request.user,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("expediente:detalle", pk=expediente.id)
    return redirect("medicina:consulta", pk=hc.pk)


@login_required
def consulta(request, pk):
    """
    Escritorio de consulta: anamnesis, examen físico, diagnósticos y plan.
    Muestra automáticamente el triaje de Enfermería si existe.
    """
    hc = get_object_or_404(
        AtencionMedicina.objects.select_related(
            "atencion__expediente__persona", "atencion__servicio"
        ),
        pk=pk,
    )
    # Sin esto, cualquier usuario autenticado abría la historia clínica de
    # cualquier paciente cambiando el id en la URL.
    verificar_acceso_atencion(request.user, hc.atencion)

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "guardar":
            hc.enfermedad_actual = request.POST.get("enfermedad_actual", "")
            hc.plan_tratamiento = request.POST.get("plan_tratamiento", "")
            hc.indicaciones = request.POST.get("indicaciones", "")
            dias = request.POST.get("dias_reposo")
            hc.dias_reposo = int(dias) if dias else None
            hc.save()
            messages.success(request, "Consulta guardada.")

        elif accion == "diagnostico":
            try:
                services.agregar_diagnostico(
                    hc.atencion,
                    request.POST["cie10"],
                    tipo=request.POST.get("tipo", "presuntivo"),
                    principal=request.POST.get("principal") == "on",
                )
                messages.success(request, "Diagnóstico agregado.")
            except (ValidationError, CIE10.DoesNotExist) as exc:
                msg = (
                    "; ".join(exc.messages)
                    if hasattr(exc, "messages")
                    else "Código CIE-10 no encontrado."
                )
                messages.error(request, msg)

        elif accion == "cerrar":
            try:
                services.cerrar_atencion(hc.atencion, usuario=request.user)
                messages.success(request, "Atención cerrada correctamente.")
                return redirect("expediente:detalle", pk=hc.atencion.expediente_id)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))

        return redirect("medicina:consulta", pk=hc.pk)

    return render(
        request,
        "medicina/consulta.html",
        {
            "hc": hc,
            "atencion": hc.atencion,
            "persona": hc.atencion.expediente.persona,
            "triaje": ultimo_triaje(hc.atencion.expediente),
            "diagnosticos": hc.atencion.diagnosticos.select_related("cie10"),
            "recetas": hc.atencion.recetas.all(),
            "ordenes": hc.atencion.ordenes_lab.all(),
        },
    )
