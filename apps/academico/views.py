"""
Asistente web de carga de la ficha socioeconómica.

Vista simple basada en plantillas Bootstrap: sube el archivo, muestra la
previsualización (altas/actualizaciones/errores) y confirma la aplicación.
Reservada al Administrador General (RBAC, informe 10).
"""

import os
import tempfile
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from apps.core.models import PeriodoAcademico
from apps.usuarios.models import Rol

from . import mapping
from .models import CargaInstitucional
from .services import LectorFicha, ProcesadorCarga, hash_archivo

# Permiso de Django que autoriza a cargar la base institucional. Se comprueba
# ADEMÁS del rol, y no en su lugar, porque hay una cuenta que legítimamente
# necesita las dos cosas a la vez y el rol solo no lo permite:
#
# La cuenta de administración con la que se prueba el sistema lleva rol
# PROFESIONAL a propósito —`rbac.es_admin()` le negaría el contenido clínico y
# vería «0 atenciones» en cada expediente—, así que por rol nunca alcanzaría
# estas pantallas. Sí tiene el permiso, que es lo que de verdad expresa
# «puede cargar la base»: más preciso que el rol, no más laxo.
#
# El sello de Psicología no se toca: estas pantallas son matrícula, no
# expediente, y el filtrado del contenido clínico sigue siendo por rol.
PERMISO_CARGA = "academico.add_cargainstitucional"


def _es_admin(user):
    """¿Puede esta cuenta cargar y consultar la base institucional?"""
    return user.is_authenticated and (
        user.is_superuser or user.rol_principal == Rol.ADMIN_GENERAL or user.has_perm(PERMISO_CARGA)
    )


@login_required
@user_passes_test(_es_admin)
def asistente(request):
    periodos = PeriodoAcademico.objects.all()
    contexto = {"periodos": periodos}

    if request.method == "POST":
        accion = request.POST.get("accion")
        periodo_id = request.POST.get("periodo")
        archivo = request.FILES.get("archivo")

        if not (periodo_id and archivo):
            messages.error(request, "Seleccione el período y el archivo.")
            return render(request, "academico/asistente.html", contexto)

        periodo = PeriodoAcademico.objects.get(pk=periodo_id)
        formato = "csv" if archivo.name.lower().endswith(".csv") else "xlsx"

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(archivo.name)[1])
        for chunk in archivo.chunks():
            tmp.write(chunk)
        tmp.close()

        try:
            carga = CargaInstitucional.objects.create(
                periodo=periodo,
                nombre_archivo=archivo.name,
                hash_archivo=hash_archivo(tmp.name),
                formato=formato,
                creado_por=request.user if request.user.is_authenticated else None,
            )
            lector = LectorFicha(tmp.name, formato)
            aplicar = accion == "aplicar"
            resultado = ProcesadorCarga(carga, carga.mapeo_columnas).procesar(
                lector, aplicar=aplicar
            )
            carga.total_filas = resultado.total
            carga.altas = resultado.altas
            carga.actualizaciones = resultado.actualizaciones
            carga.errores = resultado.errores
            carga.estado = (
                CargaInstitucional.Estado.APLICADA
                if aplicar
                else CargaInstitucional.Estado.VALIDADA
            )
            carga.bitacora = resultado.as_dict()
            carga.save()

            contexto["resultado"] = resultado.as_dict()
            contexto["aplicado"] = aplicar
            if aplicar:
                messages.success(
                    request,
                    f"Carga aplicada: {resultado.altas} altas, "
                    f"{resultado.actualizaciones} actualizaciones, "
                    f"{resultado.errores} errores, "
                    f"{resultado.alertas_generadas} alertas.",
                )
            else:
                messages.info(request, "Previsualización generada. Revise y confirme.")
        finally:
            os.unlink(tmp.name)

    return render(request, "academico/asistente.html", contexto)


@login_required
@user_passes_test(_es_admin)
def padron(request):
    """
    Lo que quedó cargado, en pantalla y paginado.

    Hasta ahora el asistente solo mostraba el resumen de la última carga —tantas
    altas, tantos errores— y no había forma de comprobar qué entró realmente sin
    entrar a la base. Esta pantalla lista fila por fila, con buscador por cédula,
    nombre, facultad o carrera.

    Es matrícula, no expediente: no muestra atenciones, diagnósticos ni el
    servicio que atiende a nadie.
    """
    from django.core.paginator import Paginator

    from . import selectors
    from .selectors import padron as consultar_padron

    texto = (request.GET.get("q") or "").strip()
    periodo_id = request.GET.get("periodo") or None
    orden = request.GET.get("orden") or selectors.ORDEN_POR_DEFECTO
    if orden not in selectors.ORDENES:
        orden = selectors.ORDEN_POR_DEFECTO
    descendente = request.GET.get("dir") == "desc"

    filtros = {c: (request.GET.get(c) or "").strip() for c in selectors.FILTROS}
    filtros = {c: v for c, v in filtros.items() if v}
    consulta = consultar_padron(texto, periodo_id, orden, descendente, filtros)
    pagina = Paginator(consulta, 50).get_page(request.GET.get("pagina"))
    return render(
        request,
        "academico/padron.html",
        {
            "pagina": pagina,
            "q": texto,
            "periodo_id": periodo_id,
            "orden": orden,
            "descendente": descendente,
            # (clave de orden, título) en el orden en que salen las columnas.
            "columnas": [
                ("cedula", "Cédula"),
                ("nombre", "Apellidos y nombres"),
                ("facultad", "Facultad"),
                ("carrera", "Carrera"),
                ("ciclo", "Ciclo"),
                ("estado", "Estado"),
                ("periodo", "Período"),
            ],
            # Lo que hay que arrastrar al cambiar de orden o de página, para no
            # perder el filtro por el camino.
            # Lo que hay que arrastrar al cambiar de orden o de página, para no
            # perder la búsqueda ni los filtros por el camino.
            "filtros": urlencode(
                {k: v for k, v in ({"q": texto, "periodo": periodo_id} | filtros).items() if v}
            ),
            "activos": filtros,
            "opciones": selectors.opciones_de_filtro(),
            "etiquetas_filtro": [
                ("facultad", "Facultad"),
                ("carrera", "Carrera"),
                ("nivel", "Nivel"),
                ("modalidad", "Modalidad"),
                ("jornada", "Jornada"),
                ("estado", "Estado"),
                ("ciclo", "Ciclo"),
                ("paralelo", "Paralelo"),
                ("sexo", "Sexo"),
                ("vinculo", "Vínculo"),
            ],
            "hay_filtro": bool(texto or periodo_id or filtros),
            "periodos": PeriodoAcademico.objects.all(),
            "total": consulta.count(),
            "cargas": CargaInstitucional.objects.select_related("periodo")[:10],
        },
    )


@login_required
@user_passes_test(_es_admin)
def diccionario(request):
    """El diccionario de columnas que debe traer el archivo, y su conteo."""
    from . import selectors

    return render(
        request,
        "academico/diccionario.html",
        {
            "grupos": selectors.diccionario(),
            "total_columnas": selectors.total_columnas(),
            "obligatorias": mapping.COLUMNAS_OBLIGATORIAS,
        },
    )


@login_required
@user_passes_test(_es_admin)
def plantilla(request):
    """
    Descarga la plantilla CSV con los encabezados exactos y una fila de ejemplo.

    Se sirve con BOM (`utf-8-sig`): sin él, Excel abre el archivo como Latin-1 y
    parte las tildes de los encabezados, y entonces el mapeo no reconoce ni
    `parroquia_procedencia`. El lector de la carga admite el BOM sin problema.
    """
    from django.http import HttpResponse

    from . import selectors

    respuesta = HttpResponse(
        selectors.plantilla_csv().encode("utf-8-sig"), content_type="text/csv; charset=utf-8"
    )
    respuesta["Content-Disposition"] = 'attachment; filename="plantilla-base-institucional.csv"'
    return respuesta


@login_required
def autocompletar(request):
    """
    Sugerencias por cédula o por nombres para los formularios del profesional.

    Exige el mismo permiso que la búsqueda de expedientes: sin él, esto sería un
    volcado del padrón institucional —nombre, carrera, correo— accesible a
    cualquier cuenta con sesión iniciada. Devuelve solo identificación y
    matrícula; nunca contenido clínico ni qué servicio atiende a la persona.
    """
    from django.http import JsonResponse

    from apps.usuarios import rbac

    from .selectors import sugerencias

    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("No tiene permisos para consultar la base institucional.")
    return JsonResponse({"resultados": sugerencias(request.GET.get("q", ""))})
