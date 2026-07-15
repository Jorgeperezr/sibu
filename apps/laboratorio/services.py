"""
Lógica de negocio de Laboratorio.

Sprint 4 implementa la SOLICITUD de exámenes desde Medicina y Odontología.
El registro/validación de resultados y el envío al correo institucional
corresponden al Sprint 5.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.expediente.models import Atencion

from .models import Examen, OrdenExamen, OrdenLaboratorio

# Regla de negocio del informe (5.2): solo Medicina y Odontología solicitan.
SERVICIOS_AUTORIZADOS = {"medicina", "odontologia"}


@transaction.atomic
def crear_orden(atencion: Atencion, examenes_ids: list[int], *,
                 prioridad: str = "rutina", diagnostico_presuntivo: str = "",
                 usuario=None) -> OrdenLaboratorio:
    """
    Crea una orden de laboratorio desde una atención de Medicina/Odontología.

    Rechaza si:
    - El servicio de la atención no está autorizado a solicitar exámenes.
    - La atención ya está firmada.
    - No se especifica ningún examen.
    """
    if atencion.servicio.codigo not in SERVICIOS_AUTORIZADOS:
        raise ValidationError(
            f"El servicio '{atencion.servicio.codigo}' no puede solicitar exámenes. "
            f"Autorizados: {sorted(SERVICIOS_AUTORIZADOS)}."
        )
    if atencion.inmutable:
        raise ValidationError("No se pueden solicitar exámenes sobre una atención firmada.")
    if not examenes_ids:
        raise ValidationError("Debe solicitar al menos un examen.")

    orden = OrdenLaboratorio.objects.create(
        atencion=atencion, prioridad=prioridad,
        diagnostico_presuntivo=diagnostico_presuntivo, creado_por=usuario,
    )
    for examen_id in examenes_ids:
        OrdenExamen.objects.create(orden=orden, examen=Examen.objects.get(pk=examen_id))
    return orden


def ordenes_pendientes():
    """Cola de órdenes por procesar en Laboratorio (Sprint 5)."""
    return (OrdenLaboratorio.objects.filter(
        estado__in=[OrdenLaboratorio.Estado.CREADA,
                    OrdenLaboratorio.Estado.MUESTRA_TOMADA,
                    OrdenLaboratorio.Estado.EN_PROCESO],
    ).select_related("atencion__expediente__persona", "atencion__servicio")
      .order_by("-prioridad", "creado_en"))
