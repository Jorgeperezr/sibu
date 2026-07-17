"""
Lógica de negocio de Farmacia (informe 5.2 M09, 6.5).

Dos responsabilidades:
1. Emisión de recetas desde la consulta (Sprint 4).
2. Inventario y despacho FEFO (Sprint 6).

FEFO (First Expired, First Out): al despachar se consumen primero los lotes
con caducidad más próxima. Es el estándar sanitario para medicamentos, y evita
que el stock caduque en percha mientras se despacha de lotes nuevos.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.expediente.models import Atencion

from .models import (
    Dispensacion,
    Lote,
    Medicamento,
    MovimientoInventario,
    Receta,
    RecetaDetalle,
)

# ============================================================
# Emisión de recetas
# ============================================================


def _siguiente_numero() -> str:
    """Numeración correlativa anual: RX-2026-000001."""
    anio = timezone.now().year
    prefijo = f"RX-{anio}-"
    ultima = Receta.objects.filter(numero__startswith=prefijo).order_by("-numero").first()
    consecutivo = int(ultima.numero.split("-")[-1]) + 1 if ultima else 1
    return f"{prefijo}{consecutivo:06d}"


@transaction.atomic
def emitir_receta(atencion: Atencion, items: list[dict], usuario=None) -> Receta:
    """
    Emite una receta electrónica desde una atención.

    `items`: [{medicamento_id, cantidad_prescrita, dosis, via, frecuencia,
               duracion, indicaciones}]
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
            raise ValidationError(f"La cantidad prescrita de {medicamento} debe ser mayor a cero.")
        RecetaDetalle.objects.create(
            receta=receta,
            medicamento=medicamento,
            cantidad_prescrita=cantidad,
            dosis=item.get("dosis", ""),
            via=item.get("via", ""),
            frecuencia=item.get("frecuencia", ""),
            duracion=item.get("duracion", ""),
            indicaciones=item.get("indicaciones", ""),
        )
    return receta


def recetas_pendientes():
    """Cola de recetas vigentes por despachar."""
    return (
        Receta.objects.filter(
            estado__in=[Receta.Estado.EMITIDA, Receta.Estado.PARCIAL],
            valida_hasta__gte=timezone.now(),
        )
        .select_related("atencion__expediente__persona")
        .prefetch_related("detalles__medicamento")
        .order_by("creado_en")
    )


def caducar_recetas_vencidas() -> int:
    """Marca como caducadas las recetas vencidas no despachadas."""
    return Receta.objects.filter(
        estado__in=[Receta.Estado.EMITIDA, Receta.Estado.PARCIAL],
        valida_hasta__lt=timezone.now(),
    ).update(estado=Receta.Estado.CADUCADA)


# ============================================================
# Inventario
# ============================================================


@transaction.atomic
def ingresar_lote(
    medicamento: Medicamento,
    numero_lote: str,
    cantidad: int,
    fecha_caducidad: date,
    *,
    usuario,
    costo_unitario=0,
    proveedor: str = "",
    referencia_doc: str = "",
) -> Lote:
    """
    Ingresa stock al inventario. Si el lote ya existe para ese medicamento,
    suma la cantidad; si no, lo crea.

    Todo ingreso deja un MovimientoInventario: el saldo del lote siempre puede
    reconstruirse desde la bitácora (trazabilidad exigida en el informe 6.5).
    """
    if cantidad <= 0:
        raise ValidationError("La cantidad a ingresar debe ser mayor a cero.")
    if fecha_caducidad <= timezone.localdate():
        raise ValidationError(
            f"No se puede ingresar un lote ya caducado (caducidad: {fecha_caducidad})."
        )

    lote, creado = Lote.objects.get_or_create(
        medicamento=medicamento,
        numero_lote=numero_lote,
        defaults={
            "fecha_caducidad": fecha_caducidad,
            "cantidad_actual": 0,
            "costo_unitario": costo_unitario,
            "proveedor": proveedor,
        },
    )
    if not creado and lote.fecha_caducidad != fecha_caducidad:
        raise ValidationError(
            f"El lote {numero_lote} ya existe con caducidad {lote.fecha_caducidad}. "
            f"Un mismo número de lote no puede tener dos fechas de caducidad."
        )

    lote.cantidad_actual += cantidad
    lote.save(update_fields=["cantidad_actual"])

    MovimientoInventario.objects.create(
        lote=lote,
        tipo=MovimientoInventario.Tipo.INGRESO,
        cantidad=cantidad,
        saldo_resultante=lote.cantidad_actual,
        referencia_doc=referencia_doc,
        usuario=usuario,
    )
    return lote


def stock_disponible(medicamento: Medicamento) -> int:
    """Stock total no caducado de un medicamento."""
    total = Lote.objects.filter(
        medicamento=medicamento,
        fecha_caducidad__gt=timezone.localdate(),
        cantidad_actual__gt=0,
    ).aggregate(total=Sum("cantidad_actual"))["total"]
    return total or 0


def lotes_fefo(medicamento: Medicamento):
    """
    Lotes disponibles ordenados por FEFO: primero los que caducan antes.

    Excluye lotes ya caducados y sin existencias.
    """
    return Lote.objects.filter(
        medicamento=medicamento,
        fecha_caducidad__gt=timezone.localdate(),
        cantidad_actual__gt=0,
    ).order_by("fecha_caducidad", "id")


def alertas_stock():
    """Medicamentos cuyo stock disponible está por debajo del mínimo."""
    alertas = []
    for medicamento in Medicamento.objects.filter(activo=True, stock_minimo__gt=0):
        disponible = stock_disponible(medicamento)
        if disponible <= medicamento.stock_minimo:
            alertas.append(
                {
                    "medicamento": medicamento,
                    "disponible": disponible,
                    "minimo": medicamento.stock_minimo,
                    "critico": disponible == 0,
                }
            )
    return alertas


def alertas_caducidad(dias: int = 90):
    """Lotes con existencias que caducan dentro de los próximos N días."""
    limite = timezone.localdate() + timedelta(days=dias)
    return (
        Lote.objects.filter(
            cantidad_actual__gt=0,
            fecha_caducidad__lte=limite,
            fecha_caducidad__gt=timezone.localdate(),
        )
        .select_related("medicamento")
        .order_by("fecha_caducidad")
    )


@transaction.atomic
def dar_de_baja_caducados(usuario) -> int:
    """
    Da de baja los lotes caducados con existencias. Devuelve las unidades
    dadas de baja. Deja movimiento de tipo BAJA para la trazabilidad.
    """
    unidades = 0
    caducados = Lote.objects.filter(
        fecha_caducidad__lte=timezone.localdate(), cantidad_actual__gt=0
    )
    for lote in caducados:
        cantidad = lote.cantidad_actual
        lote.cantidad_actual = 0
        lote.save(update_fields=["cantidad_actual"])
        MovimientoInventario.objects.create(
            lote=lote,
            tipo=MovimientoInventario.Tipo.BAJA,
            cantidad=-cantidad,
            saldo_resultante=0,
            referencia_doc="Baja automática por caducidad",
            usuario=usuario,
        )
        unidades += cantidad
    return unidades


# ============================================================
# Despacho FEFO
# ============================================================


def _cantidad_ya_despachada(detalle: RecetaDetalle) -> int:
    total = detalle.dispensaciones.aggregate(total=Sum("cantidad_despachada"))["total"]
    return total or 0


def pendiente_por_despachar(detalle: RecetaDetalle) -> int:
    """Unidades que aún faltan por entregar de un ítem de la receta."""
    return max(detalle.cantidad_prescrita - _cantidad_ya_despachada(detalle), 0)


@transaction.atomic
def despachar_item(detalle: RecetaDetalle, cantidad: int, *, usuario) -> list[Dispensacion]:
    """
    Despacha un ítem de la receta consumiendo lotes por FEFO.

    Puede repartir la cantidad entre varios lotes si el primero no alcanza.
    Devuelve la lista de dispensaciones creadas (una por lote consumido).

    Reglas:
    - La receta debe estar vigente y en estado despachable.
    - No se puede despachar más de lo prescrito.
    - No se puede despachar sin stock suficiente.
    """
    receta = detalle.receta

    if receta.estado not in {Receta.Estado.EMITIDA, Receta.Estado.PARCIAL}:
        raise ValidationError(f"La receta está {receta.get_estado_display()} y no admite despacho.")
    if receta.valida_hasta < timezone.now():
        raise ValidationError(
            f"La receta {receta.numero} caducó el {receta.valida_hasta:%d/%m/%Y %H:%M}."
        )
    if cantidad <= 0:
        raise ValidationError("La cantidad a despachar debe ser mayor a cero.")

    pendiente = pendiente_por_despachar(detalle)
    if cantidad > pendiente:
        raise ValidationError(
            f"Solo quedan {pendiente} unidades por despachar de {detalle.medicamento} "
            f"(prescritas {detalle.cantidad_prescrita})."
        )

    disponible = stock_disponible(detalle.medicamento)
    if cantidad > disponible:
        raise ValidationError(
            f"Stock insuficiente de {detalle.medicamento}: "
            f"disponible {disponible}, solicitado {cantidad}."
        )

    dispensaciones = []
    restante = cantidad
    for lote in lotes_fefo(detalle.medicamento).select_for_update():
        if restante <= 0:
            break
        toma = min(lote.cantidad_actual, restante)

        lote.cantidad_actual -= toma
        lote.save(update_fields=["cantidad_actual"])

        MovimientoInventario.objects.create(
            lote=lote,
            tipo=MovimientoInventario.Tipo.EGRESO,
            cantidad=-toma,
            saldo_resultante=lote.cantidad_actual,
            referencia_doc=receta.numero,
            usuario=usuario,
        )
        dispensaciones.append(
            Dispensacion.objects.create(
                receta_detalle=detalle,
                lote=lote,
                cantidad_despachada=toma,
                despachado_por=usuario,
            )
        )
        restante -= toma

    _actualizar_estado_receta(receta)
    return dispensaciones


def _actualizar_estado_receta(receta: Receta) -> Receta:
    """Recalcula el estado de la receta a partir de lo despachado."""
    detalles = receta.detalles.all()
    pendientes = sum(pendiente_por_despachar(d) for d in detalles)
    despachado_algo = any(_cantidad_ya_despachada(d) > 0 for d in detalles)

    if pendientes == 0:
        receta.estado = Receta.Estado.DESPACHADA
    elif despachado_algo:
        receta.estado = Receta.Estado.PARCIAL
    else:
        receta.estado = Receta.Estado.EMITIDA
    receta.save(update_fields=["estado", "actualizado_en"])
    return receta


@transaction.atomic
def despachar_receta_completa(receta: Receta, *, usuario) -> dict:
    """
    Intenta despachar todo lo pendiente de la receta.

    Devuelve un resumen con lo entregado y lo que quedó pendiente por falta de
    stock (no falla: entrega lo que hay y deja el resto pendiente, que es como
    opera la farmacia real).
    """
    resumen = {"despachado": [], "sin_stock": []}
    for detalle in receta.detalles.select_related("medicamento"):
        pendiente = pendiente_por_despachar(detalle)
        if pendiente == 0:
            continue
        disponible = stock_disponible(detalle.medicamento)
        entregar = min(pendiente, disponible)
        if entregar > 0:
            despachar_item(detalle, entregar, usuario=usuario)
            resumen["despachado"].append(
                {"medicamento": str(detalle.medicamento), "cantidad": entregar}
            )
        if entregar < pendiente:
            resumen["sin_stock"].append(
                {
                    "medicamento": str(detalle.medicamento),
                    "faltante": pendiente - entregar,
                }
            )
    _actualizar_estado_receta(receta)
    return resumen


def anular_receta(receta: Receta, motivo: str) -> Receta:
    """Anula una receta no despachada (error de prescripción)."""
    if not motivo:
        raise ValidationError("Debe indicar el motivo de la anulación.")
    if receta.estado in {Receta.Estado.DESPACHADA, Receta.Estado.PARCIAL}:
        raise ValidationError("No se puede anular una receta ya despachada total o parcialmente.")
    receta.estado = Receta.Estado.ANULADA
    receta.save(update_fields=["estado", "actualizado_en"])
    return receta
