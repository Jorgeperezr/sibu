"""Interfaz web de firma electrónica."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.expediente.models import Atencion
from apps.usuarios.decorators import verificar_acceso_atencion

from . import services
from .models import SolicitudFirma


@login_required
def solicitar(request, atencion_id):
    """Genera el PDF del informe y abre el panel de firma."""
    atencion = get_object_or_404(
        Atencion.objects.select_related("expediente__persona", "servicio", "profesional__usuario"),
        pk=atencion_id,
    )
    verificar_acceso_atencion(request.user, atencion)

    try:
        pdf = services.generar_pdf(
            "firma/informe_atencion.html",
            {"atencion": atencion, "persona": atencion.expediente.persona},
        )
        solicitud = services.preparar_solicitud(
            atencion=atencion,
            solicitante=request.user,
            pdf=pdf,
            documento_ref_tipo="atencion",
            documento_ref_id=atencion.pk,
            tipo_documento="informe-atencion",
            razon=f"Informe de {atencion.servicio.nombre}",
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("expediente:detalle", pk=atencion.expediente_id)
    return redirect("firma:panel", pk=solicitud.pk)


@login_required
def panel(request, pk):
    """Muestra el botón "Firmar electrónicamente" y espera el retorno."""
    solicitud = get_object_or_404(
        SolicitudFirma.objects.select_related(
            "atencion__expediente__persona", "atencion__servicio"
        ),
        pk=pk,
    )
    verificar_acceso_atencion(request.user, solicitud.atencion)

    enlace = None
    if request.method == "POST" and solicitud.abierta:
        try:
            enlace = services.solicitar_token(solicitud)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))

    return render(
        request,
        "firma/panel.html",
        {
            "solicitud": solicitud,
            "enlace": enlace,
            "firma": getattr(solicitud, "firma", None),
        },
    )


@login_required
def descargar(request, pk):
    """Entrega el PDF firmado."""
    solicitud = get_object_or_404(SolicitudFirma.objects.select_related("atencion"), pk=pk)
    verificar_acceso_atencion(request.user, solicitud.atencion)

    if solicitud.estado != SolicitudFirma.Estado.FIRMADA or not solicitud.pdf_firmado:
        messages.error(request, "Este documento todavía no está firmado.")
        return redirect("firma:panel", pk=pk)

    from apps.auditoria.models import LogAuditoria

    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="firma",
        entidad="SolicitudFirma",
        entidad_id=str(solicitud.pk),
        expediente_id=solicitud.atencion.expediente_id,
        detalle={"hash_firmado": solicitud.hash_firmado},
    )
    respuesta = HttpResponse(bytes(solicitud.pdf_firmado), content_type="application/pdf")
    respuesta["Content-Disposition"] = f'inline; filename="{solicitud.nombre_documento}"'
    return respuesta
