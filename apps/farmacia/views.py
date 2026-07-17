"""Interfaz web de Farmacia: mostrador de despacho e inventario."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from . import services
from .models import Lote, Medicamento, Receta, RecetaDetalle


@login_required
def mostrador(request):
    """Cola de recetas por despachar."""
    return render(
        request,
        "farmacia/mostrador.html",
        {
            "recetas": services.recetas_pendientes(),
            "alertas_stock": services.alertas_stock(),
        },
    )


@login_required
def despachar(request, pk):
    """Ficha de la receta: despacho ítem por ítem con FEFO."""
    receta = get_object_or_404(
        Receta.objects.select_related("atencion__expediente__persona").prefetch_related(
            "detalles__medicamento", "detalles__dispensaciones__lote"
        ),
        pk=pk,
    )
    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        if perfil is None:
            messages.error(request, "Su usuario no tiene perfil profesional asignado.")
            return redirect("farmacia:despachar", pk=receta.pk)

        accion = request.POST.get("accion")
        try:
            if accion == "despachar_item":
                detalle = receta.detalles.get(pk=request.POST["detalle"])
                dispensaciones = services.despachar_item(
                    detalle, int(request.POST["cantidad"]), usuario=perfil
                )
                lotes = ", ".join(
                    f"{d.lote.numero_lote} ({d.cantidad_despachada})" for d in dispensaciones
                )
                messages.success(request, f"Despachado de lote(s): {lotes}")

            elif accion == "despachar_todo":
                resumen = services.despachar_receta_completa(receta, usuario=perfil)
                if resumen["despachado"]:
                    messages.success(request, f"Despachados {len(resumen['despachado'])} ítem(s).")
                for faltante in resumen["sin_stock"]:
                    messages.warning(
                        request,
                        f"Sin stock suficiente de {faltante['medicamento']}: "
                        f"faltan {faltante['faltante']} unidades.",
                    )

            elif accion == "anular":
                services.anular_receta(receta, request.POST.get("motivo", ""))
                messages.warning(request, "Receta anulada.")

        except (ValidationError, RecetaDetalle.DoesNotExist) as exc:
            msg = "; ".join(exc.messages) if hasattr(exc, "messages") else "Ítem no encontrado."
            messages.error(request, msg)
        return redirect("farmacia:despachar", pk=receta.pk)

    items = []
    for detalle in receta.detalles.select_related("medicamento"):
        items.append(
            {
                "detalle": detalle,
                "pendiente": services.pendiente_por_despachar(detalle),
                "stock": services.stock_disponible(detalle.medicamento),
                "lotes_fefo": services.lotes_fefo(detalle.medicamento)[:3],
            }
        )

    return render(
        request,
        "farmacia/despachar.html",
        {
            "receta": receta,
            "persona": receta.atencion.expediente.persona,
            "items": items,
            "Estado": Receta.Estado,
        },
    )


@login_required
def inventario(request):
    """Inventario por lote con alertas de caducidad."""
    medicamentos = []
    for medicamento in Medicamento.objects.filter(activo=True).order_by("dci"):
        disponible = services.stock_disponible(medicamento)
        medicamentos.append(
            {
                "medicamento": medicamento,
                "disponible": disponible,
                "bajo_minimo": 0 < medicamento.stock_minimo >= disponible,
                "sin_stock": disponible == 0,
            }
        )
    return render(
        request,
        "farmacia/inventario.html",
        {
            "medicamentos": medicamentos,
            "por_caducar": services.alertas_caducidad(90),
            "lotes": Lote.objects.select_related("medicamento")
            .filter(cantidad_actual__gt=0)
            .order_by("fecha_caducidad")[:50],
        },
    )
