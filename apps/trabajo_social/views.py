"""Interfaz web de Trabajo Social: ficha socioeconómica versionada."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.usuarios.decorators import verificar_es_del_servicio

from . import services


def _campos_json(post, prefijo):
    """Reconstruye un dict desde campos del formulario tipo `prefijo-clave`."""
    datos = {}
    for clave, valor in post.items():
        if clave.startswith(f"{prefijo}-") and valor.strip():
            datos[clave.removeprefix(f"{prefijo}-")] = valor.strip()
    return datos


@login_required
def ficha(request, expediente_id):
    """Ficha vigente + historial de versiones."""
    servicio = get_object_or_404(Servicio, codigo="trabajo-social")
    verificar_es_del_servicio(request.user, servicio)
    expediente = get_object_or_404(Expediente.objects.select_related("persona"), pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        raise PermissionDenied("Su usuario no tiene perfil profesional.")

    if request.method == "POST":
        try:
            if request.POST.get("accion") == "prepoblar":
                services.prepoblar_desde_matricula(expediente, usuario=request.user)
                messages.success(request, "Ficha v1 creada con los datos declarados en matrícula.")
            else:
                datos = {
                    "ingresos": _campos_json(request.POST, "ingreso"),
                    "egresos": _campos_json(request.POST, "egreso"),
                    "convivencia": {"numero_miembros": request.POST.get("numero_miembros", "1")},
                }
                nueva = services.verificar_ficha(
                    expediente, datos, profesional=perfil, usuario=request.user
                )
                messages.success(
                    request,
                    f"Versión {nueva.version} registrada. "
                    f"Puntaje {nueva.puntaje} SBU — {nueva.estrato}. "
                    f"La versión anterior se conserva.",
                )
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("trabajo_social:ficha", expediente_id=expediente_id)

    vigente = services.ficha_vigente(expediente)
    return render(
        request,
        "trabajo_social/ficha.html",
        {
            "expediente": expediente,
            "vigente": vigente,
            "historial": services.historial_fichas(expediente),
        },
    )
