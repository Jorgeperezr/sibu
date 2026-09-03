"""
Ficha propia del profesional.

Cada profesional mantiene aquí lo que le identifica al atender y al firmar:
título, registro profesional y cédula. Antes solo se podía cargar desde el
panel de administración, así que en la práctica quedaba vacío.

Lo que NO se edita aquí son los servicios, la sección y el rol: de ellos
depende el RBAC, y una pantalla que los dejara tocar sería una vía para
ampliarse el acceso a uno mismo. Se muestran, en solo lectura, para que el
profesional pueda comprobar con qué permisos trabaja.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from .models import PerfilProfesional
from .services import CAMPOS_CUENTA, CAMPOS_PERFIL, actualizar_mi_perfil


@login_required
def mi_perfil(request):
    if request.method == "POST":
        datos = {c: request.POST.get(c, "") for c in CAMPOS_CUENTA + CAMPOS_PERFIL}
        try:
            actualizar_mi_perfil(request.user, datos)
            messages.success(request, "Sus datos quedaron actualizados.")
            return redirect("usuarios:mi_perfil")
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))

    perfil = (
        PerfilProfesional.objects.filter(usuario=request.user)
        .select_related("seccion")
        .prefetch_related("servicios")
        .first()
    )
    return render(
        request,
        "usuarios/mi_perfil.html",
        {"perfil": perfil, "servicios": perfil.servicios.all() if perfil else []},
    )
