"""
Asistente web de carga de la ficha socioeconómica.

Vista simple basada en plantillas Bootstrap: sube el archivo, muestra la
previsualización (altas/actualizaciones/errores) y confirma la aplicación.
Reservada al Administrador General (RBAC, informe 10).
"""
import os
import tempfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import redirect, render

from apps.core.models import PeriodoAcademico
from apps.usuarios.models import Rol

from .models import CargaInstitucional
from .services import LectorFicha, ProcesadorCarga, hash_archivo


def _es_admin(user):
    return user.is_authenticated and (
        user.is_superuser or user.rol_principal == Rol.ADMIN_GENERAL
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

        tmp = tempfile.NamedTemporaryFile(delete=False,
                                          suffix=os.path.splitext(archivo.name)[1])
        for chunk in archivo.chunks():
            tmp.write(chunk)
        tmp.close()

        try:
            carga = CargaInstitucional.objects.create(
                periodo=periodo, nombre_archivo=archivo.name,
                hash_archivo=hash_archivo(tmp.name), formato=formato,
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
            carga.estado = (CargaInstitucional.Estado.APLICADA if aplicar
                            else CargaInstitucional.Estado.VALIDADA)
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
