"""
Lógica de negocio de Farmacia.

En el Sprint 4 se implementa la EMISIÓN de recetas desde Medicina. El
despacho con descuento de inventario (FEFO) corresponde al Sprint 6.
"""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.expediente.models import Atencion

from .models import Medicamento, Receta, RecetaDetalle


def _siguiente_numero() -> str:
    """Numeración correlativa anual: RX-2026-000001."""
    anio = timezone.now().year
    prefijo = f"RX-{anio}-"
    ultima = (Receta.objects.filter(numero__startswith=prefijo)
              .order_by("-numero").first())
    consecutivo = int(ultima.numero.split("-")[-1]) + 1 if ultima else 1
    return f"{prefijo}{consecutivo:06d}"


@transaction.atomic
def emitir_receta(atencion: Atencion, items: list[dict], usuario=None) -> Receta:
    """
    Emite una receta electrónica desde una atención.

    `items`: [{medicamento_id, cantidad_prescrita, dosis, via, frecuencia,
               duracion, indicaciones}]

    Reglas (informe 6.5):
    - Solo desde atenciones no firmadas (la receta forma parte de la consulta).
    - Debe tener al menos un ítem.
    - Vigencia configurable (SIBU.RECETA_VALIDEZ_HORAS, por defecto 72 h).
    """
    if atencion.inmutable:
        raise ValidationError("No se puede emitir una receta sobre una atención firmada.")
    if not items:
        raise ValidationError("La receta debe tener al menos un medicamento.")

    horas = settings.SIBU.get("RECETA_VALIDEZ_HORAS", 72)
    receta = Receta.objects.create(
        atencion=atencion,
        numero=_siguiente_numero(),
        valida_hasta=timezone.now() + timedelta(hours=horas),
        creado_por=usuario,
    )

    for item in items:
        medicamento = Medicamento.objects.get(pk=item["medicamento_id"])
        cantidad = int(item.get("cantidad_prescrita", 0))
        if cantidad <= 0:
            raise ValidationError(
                f"La cantidad prescrita de {medicamento} debe ser mayor a cero."
            )
        RecetaDetalle.objects.create(
            receta=receta, medicamento=medicamento,
            cantidad_prescrita=cantidad,
            dosis=item.get("dosis", ""), via=item.get("via", ""),
            frecuencia=item.get("frecuencia", ""), duracion=item.get("duracion", ""),
            indicaciones=item.get("indicaciones", ""),
        )
    return receta


def recetas_pendientes():
    """Cola de recetas vigentes por despachar (usada por Farmacia, Sprint 6)."""
    return (Receta.objects.filter(
        estado__in=[Receta.Estado.EMITIDA, Receta.Estado.PARCIAL],
        valida_hasta__gte=timezone.now(),
    ).select_related("atencion__expediente__persona").order_by("creado_en"))


def caducar_recetas_vencidas() -> int:
    """Marca como caducadas las recetas vencidas no despachadas."""
    return Receta.objects.filter(
        estado__in=[Receta.Estado.EMITIDA, Receta.Estado.PARCIAL],
        valida_hasta__lt=timezone.now(),
    ).update(estado=Receta.Estado.CADUCADA)
