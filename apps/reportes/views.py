"""Tablero de gestión. Solo roles directivos; solo agregados."""

import csv
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.auditoria.models import LogAuditoria
from apps.core.models import Servicio
from apps.core.pdf import render_pdf
from apps.usuarios import rbac
from apps.usuarios.models import Rol
from apps.usuarios.rbac import servicios_del_usuario

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


def _mis_servicios(user):
    """
    Los servicios del profesional, o 403 si no tiene ninguno.

    El informe demográfico es distinto del tablero: aquí no hace falta ser
    Dirección, basta con pertenecer al servicio que se va a informar —es el
    mismo contenido que ya se ve atención por atención, solo que sumado—.
    """
    mis = Servicio.objects.filter(pk__in=servicios_del_usuario(user))
    if not mis:
        raise PermissionDenied("Su usuario no tiene servicios asignados.")
    return mis


def _servicio_o_403(request, mis_servicios):
    servicio_id = request.GET.get("servicio") or mis_servicios[0].pk
    servicio = mis_servicios.filter(pk=servicio_id).first()
    if servicio is None:
        raise PermissionDenied("Ese servicio no le corresponde.")
    return servicio


@login_required
def informe_servicio(request):
    """Perfil demográfico de las atenciones de un servicio propio, por fechas."""
    mis_servicios = _mis_servicios(request.user)
    servicio = _servicio_o_403(request, mis_servicios)
    desde, hasta = _rango(request)
    return render(
        request,
        "reportes/informe_servicio.html",
        {
            "datos": services.informe_estadistico(servicio, desde, hasta),
            "servicios": mis_servicios,
            "servicio": servicio,
            "desde": desde,
            "hasta": hasta,
        },
    )


@login_required
def informe_servicio_pdf(request):
    """El informe demográfico como documento formal, con membrete institucional."""
    mis_servicios = _mis_servicios(request.user)
    servicio = _servicio_o_403(request, mis_servicios)
    desde, hasta = _rango(request)
    datos = services.informe_estadistico(servicio, desde, hasta)

    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="InformeEstadistico",
        entidad_id=servicio.codigo,
        detalle={"desde": str(desde or ""), "hasta": str(hasta or "")},
    )

    pdf = render_pdf("reportes/informe_servicio_pdf.html", {"datos": datos})
    respuesta = HttpResponse(pdf, content_type="application/pdf")
    nombre = f"informe-demografico-{servicio.codigo}-{timezone.localdate():%Y%m%d}.pdf"
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@login_required
def exportar_hoja(request):
    """
    Vuelca el historial de atenciones a una hoja de Google compartida.

    Lo abre quien atiende, no la Dirección, y no es un olvido: el historial que
    se exporta es el que cada uno ve, y `rbac.atenciones_visibles` le devuelve
    cero a quien gobierna por separación de funciones. La Dirección tiene el
    tablero y su CSV de agregados.

    La pantalla dice, antes de pulsar nada, cuántas filas saldrían, cuántas se
    retienen por confidencialidad y qué implica compartir la hoja. Eso último
    importa: a partir del volcado SIBU no controla quién lo lee, no puede
    impedir que lo modifiquen y no puede revocarlo.
    """
    from . import exportacion

    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("La exportación del historial es para el personal de la Unidad.")

    desde, hasta = _rango(request)

    if request.GET.get("formato") == "csv":
        return _historial_csv(request, desde, hasta)

    proveedor = exportacion.get_proveedor()
    contexto = {
        "resumen": exportacion.resumen_de_exportacion(request.user, desde, hasta),
        "encabezados": exportacion.ENCABEZADOS,
        "desde": desde,
        "hasta": hasta,
        "proveedor": proveedor,
        "disponible": proveedor.disponible(),
        "motivo": "" if proveedor.disponible() else proveedor.motivo_no_disponible(),
    }

    if request.method == "POST":
        try:
            hoja_id = exportacion.id_de_hoja(request.POST.get("enlace", ""))
            filas = exportacion.historial(request.user, desde, hasta)
            url = proveedor.volcar(
                hoja_id,
                exportacion.ENCABEZADOS,
                [[fila[c] for c in exportacion.ENCABEZADOS] for fila in filas],
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            # Sacar el historial de la Unidad es de lo que más falta hace poder
            # revisar después: quién, cuándo, cuántas filas y a qué hoja.
            LogAuditoria.objects.create(
                usuario=request.user,
                accion=LogAuditoria.Accion.EXPORT,
                modulo="reportes",
                entidad="HistorialAtenciones",
                entidad_id=hoja_id,
                detalle={
                    "hoja": hoja_id,
                    "filas": len(filas),
                    "retenidas": contexto["resumen"]["retenidas_por_confidencialidad"],
                    "desde": str(desde or ""),
                    "hasta": str(hasta or ""),
                },
            )
            messages.success(request, f"{len(filas)} atención(es) volcadas en la hoja.")
            contexto["url_hoja"] = url

    return render(request, "reportes/exportar_hoja.html", contexto)


def _historial_csv(request, desde, hasta):
    """
    El mismo historial, descargado en vez de volcado.

    Existe porque sin credenciales de Google la pantalla no puede volcar nada,
    y decirle al usuario «descargue el CSV» sin darle el botón sería mandarlo a
    un sitio que no está. Lleva exactamente las mismas filas y el mismo filtro:
    es la misma exportación por otro camino, no una puerta más ancha.
    """
    from . import exportacion

    filas = exportacion.historial(request.user, desde, hasta)
    LogAuditoria.objects.create(
        usuario=request.user,
        accion=LogAuditoria.Accion.EXPORT,
        modulo="reportes",
        entidad="HistorialAtenciones",
        entidad_id="csv",
        detalle={
            "formato": "csv",
            "filas": len(filas),
            "retenidas": exportacion.resumen_de_exportacion(request.user, desde, hasta)[
                "retenidas_por_confidencialidad"
            ],
            "desde": str(desde or ""),
            "hasta": str(hasta or ""),
        },
    )

    respuesta = HttpResponse(content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = (
        f'attachment; filename="historial-atenciones-{timezone.localdate()}.csv"'
    )
    # BOM: sin él, Excel en Windows abre el archivo en Latin-1 y parte las
    # tildes de «atención» y de los apellidos. Es el mismo cuidado que ya se
    # tiene con la plantilla de carga.
    respuesta.write("\ufeff")
    escritor = csv.writer(respuesta)
    escritor.writerow(exportacion.ENCABEZADOS)
    for fila in filas:
        escritor.writerow([fila[c] for c in exportacion.ENCABEZADOS])
    return respuesta
