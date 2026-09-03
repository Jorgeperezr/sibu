"""
Ficha propia del profesional.

Cada profesional mantiene aquí lo que le identifica al atender y al firmar:
título, registro profesional, cédula y —desde hoy— fecha de nacimiento,
denominación del cargo y las actividades esenciales de su manual de puestos.
Antes solo se podía cargar desde el panel de administración, así que en la
práctica quedaba vacío.

Lo que NO se edita aquí son los servicios, la sección y el rol: de ellos
depende el RBAC, y una pantalla que los dejara tocar sería una vía para
ampliarse el acceso a uno mismo. Se muestran, en solo lectura, para que el
profesional pueda comprobar con qué permisos trabaja.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from .models import ActividadEsencial, PerfilProfesional
from .services import (
    CAMPOS_CUENTA,
    CAMPOS_PERFIL,
    actualizar_mi_perfil,
    agregar_actividad,
    eliminar_actividad,
)


def _mi_perfil_o_404(request):
    """El PerfilProfesional del usuario en sesión, o 404 si no tiene."""
    return get_object_or_404(PerfilProfesional, usuario=request.user)


@login_required
def mi_perfil(request):
    if request.method == "POST":
        accion = request.POST.get("accion", "actualizar")
        try:
            if accion == "actualizar":
                datos = {c: request.POST.get(c, "") for c in CAMPOS_CUENTA + CAMPOS_PERFIL}
                actualizar_mi_perfil(request.user, datos)
                messages.success(request, "Sus datos quedaron actualizados.")

            elif accion == "agregar_actividad":
                perfil = _mi_perfil_o_404(request)
                agregar_actividad(perfil, request.POST.get("descripcion", ""))
                messages.success(request, "Actividad agregada.")

            elif accion == "agregar_subactividad":
                perfil = _mi_perfil_o_404(request)
                superior = get_object_or_404(
                    ActividadEsencial, pk=request.POST.get("actividad_superior"), perfil=perfil
                )
                agregar_actividad(
                    perfil, request.POST.get("descripcion", ""), actividad_superior=superior
                )
                messages.success(request, "Sub-actividad agregada.")

            elif accion == "eliminar_actividad":
                perfil = _mi_perfil_o_404(request)
                actividad = get_object_or_404(
                    ActividadEsencial, pk=request.POST.get("actividad"), perfil=perfil
                )
                eliminar_actividad(actividad)
                messages.success(request, "Actividad eliminada.")

        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("usuarios:mi_perfil")

    perfil = (
        PerfilProfesional.objects.filter(usuario=request.user)
        .select_related("seccion")
        .prefetch_related("servicios")
        .first()
    )
    # Solo de primer nivel: cada una trae sus `subactividades` prefetched, en
    # el orden que ya fija `Meta.ordering` del modelo.
    actividades = (
        ActividadEsencial.objects.filter(perfil=perfil, actividad_superior=None)
        .prefetch_related("subactividades")
        .order_by("orden")
        if perfil
        else []
    )
    return render(
        request,
        "usuarios/mi_perfil.html",
        {
            "perfil": perfil,
            "servicios": perfil.servicios.all() if perfil else [],
            "actividades": actividades,
        },
    )
