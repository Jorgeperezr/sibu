"""
Lógica de negocio de Psicopedagogía (informe 6.7).

El valor del módulo está en medir impacto: el seguimiento compara el promedio
académico antes y después de la intervención, lo que alimenta los indicadores
de la Unidad (S9).
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import PeriodoAcademico, Servicio
from apps.expediente.models import Atencion, Expediente
from apps.expediente.services import construir_snapshot
from apps.usuarios.models import PerfilProfesional

from .models import FichaPsicopedagogica, SeguimientoAcademico


@transaction.atomic
def crear_ficha(
    *, expediente: Expediente, profesional: PerfilProfesional, motivo: str = "", usuario=None
) -> FichaPsicopedagogica:
    """Abre una ficha psicopedagógica (Atencion + Ficha)."""
    try:
        servicio = Servicio.objects.get(codigo="psicopedagogia")
    except Servicio.DoesNotExist as exc:
        raise ValidationError("El servicio 'psicopedagogia' no está configurado.") from exc

    atencion = Atencion.objects.create(
        expediente=expediente,
        servicio=servicio,
        profesional=profesional,
        fecha_hora=timezone.now(),
        motivo_consulta=motivo,
        snapshot_academico=construir_snapshot(expediente.persona),
        creado_por=usuario,
    )
    return FichaPsicopedagogica.objects.create(
        atencion=atencion,
        motivo=motivo[:255],
        historial_academico=_historial_desde_academico(expediente),
    )


def _historial_desde_academico(expediente: Expediente) -> dict:
    """
    Toma el historial académico de los datos institucionales ya cargados.

    No inventa: si no hay datos académicos, devuelve un dict vacío y el
    profesional lo completa.
    """
    from apps.academico.models import DatoAcademico

    datos = (
        DatoAcademico.objects.filter(persona=expediente.persona)
        .select_related("periodo")
        .order_by("-periodo__codigo")[:5]
    )
    return {
        d.periodo.codigo: {
            "carrera": d.carrera,
            "nivel": d.nivel,
            "promedio": str(d.promedio) if d.promedio is not None else None,
        }
        for d in datos
    }


def registrar_seguimiento(
    ficha: FichaPsicopedagogica,
    periodo: str,
    *,
    promedio_antes=None,
    promedio_despues=None,
    observaciones: str = "",
) -> SeguimientoAcademico:
    """
    Registra el seguimiento de un periodo.

    Un mismo periodo no se duplica: si ya existe, se actualiza.
    """
    if ficha.atencion.inmutable:
        raise ValidationError("No se puede modificar una atención firmada.")
    if not PeriodoAcademico.objects.filter(codigo=periodo).exists():
        raise ValidationError(f"El periodo académico '{periodo}' no existe.")

    for etiqueta, valor in (("antes", promedio_antes), ("después", promedio_despues)):
        if valor is not None and not (Decimal("0") <= Decimal(str(valor)) <= Decimal("10")):
            raise ValidationError(f"El promedio {etiqueta} debe estar entre 0 y 10.")

    seguimiento, _ = SeguimientoAcademico.objects.update_or_create(
        ficha=ficha,
        periodo=periodo,
        defaults={
            "promedio_antes": promedio_antes,
            "promedio_despues": promedio_despues,
            "observaciones": observaciones,
        },
    )
    return seguimiento


def impacto(ficha: FichaPsicopedagogica) -> dict:
    """
    Mide el impacto de la intervención: variación del promedio.

    Solo considera seguimientos con ambos promedios registrados; los demás no
    son comparables y se cuentan aparte para no falsear el indicador.
    """
    seguimientos = ficha.seguimientos.all()
    comparables = [
        s for s in seguimientos if s.promedio_antes is not None and s.promedio_despues is not None
    ]
    if not comparables:
        return {
            "comparables": 0,
            "incompletos": seguimientos.count(),
            "variacion_promedio": None,
            "mejoro": None,
        }

    deltas = [s.promedio_despues - s.promedio_antes for s in comparables]
    variacion = sum(deltas) / len(deltas)
    return {
        "comparables": len(comparables),
        "incompletos": seguimientos.count() - len(comparables),
        "variacion_promedio": variacion.quantize(Decimal("0.01")),
        "mejoro": variacion > 0,
        "detalle": [
            {
                "periodo": s.periodo,
                "antes": s.promedio_antes,
                "despues": s.promedio_despues,
                "delta": s.promedio_despues - s.promedio_antes,
            }
            for s in comparables
        ],
    }
