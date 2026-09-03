"""Tablero de gestión. Solo roles directivos; solo agregados."""

import csv
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.core.pdf import render_pdf
from apps.usuarios.models import Rol

from . import services

ROLES_TABLERO = {Rol.ADMIN_GENERAL, Rol.DIRECTOR, Rol.COORDINADOR}


def _solo_directivos(user):
    if user.rol_principal not in ROLES_TABLERO:
        raise PermissionDenied("El tablero de gestión es para la Dirección y las Coordinaciones.")


def _rango(request):
    desde = hasta = None
    try:
        if request.GET.get("desde"):
            desde = datetime.strptime(request.GET["desde"], "%Y-%m-%d").date()
        if request.GET.get("hasta"):
            hasta = datetime.strptime(request.GET["hasta"], "%Y-%m-%d").date()
    except ValueError:
        pass
    return desde, hasta


@login_required
def tablero(request):
    _solo_directivos(request.user)
    desde, hasta = _rango(request)
    return render(
        request,
        "reportes/tablero.html",
        {"datos": services.tablero_general(desde, hasta), "desde": desde, "hasta": hasta},
    )


@login_required
def exportar_pdf(request):
    """
    El tablero como documento formal, con el membrete institucional.

    El CSV sirve para seguir trabajando los datos; este PDF es el que se
    archiva o se entrega. Los conteos llegan ya suprimidos desde `services`, así
    que el documento no puede publicar una cifra que la pantalla oculta.
    """
    _solo_directivos(request.user)
    desde, hasta = _rango(request)

    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="TableroGeneral",
        entidad_id="pdf",
        detalle={"desde": str(desde or ""), "hasta": str(hasta or "")},
    )

    pdf = render_pdf(
        "reportes/tablero_pdf.html",
        {
            "datos": services.tablero_general(desde, hasta),
            "desde": desde,
            "hasta": hasta,
            "k_minimo": services.K_MINIMO,
        },
    )
    respuesta = HttpResponse(pdf, content_type="application/pdf")
    nombre = f"reporte-gestion-{timezone.localdate():%Y%m%d}.pdf"
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@login_required
def exportar_csv(request):
    """Atenciones por servicio en CSV. La exportación queda auditada."""
    _solo_directivos(request.user)
    desde, hasta = _rango(request)
    filas = services.atenciones_por_servicio(desde, hasta)

    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="TableroGeneral",
        entidad_id="csv",
        detalle={"desde": str(desde or ""), "hasta": str(hasta or "")},
    )
    respuesta = HttpResponse(content_type="text/csv")
    respuesta["Content-Disposition"] = 'attachment; filename="atenciones_por_servicio.csv"'
    w = csv.writer(respuesta)
    w.writerow(["servicio", "atenciones", "pacientes_distintos"])
    for f in filas:
        w.writerow([f["servicio"], f["total"], f["pacientes"]])
    return respuesta
