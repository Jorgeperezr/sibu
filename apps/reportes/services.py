"""
Indicadores agregados para la gestión de la Unidad.

Regla de confidencialidad que gobierna el módulo: los tableros muestran
GESTIÓN, no contenido clínico. Psicología aparece solo como conteos agregados
—la Dirección necesita saber cuánta demanda atiende el servicio— y en los
desgloses finos se aplica supresión de celdas pequeñas: un cruce (carrera ×
periodo, por ejemplo) con menos de K_MINIMO casos en un servicio confidencial
no se muestra, porque un conteo de 1 identifica a la persona tan bien como su
nombre.
"""

from django.db.models import Count, Q
from django.utils import timezone

from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES

K_MINIMO = 5  # umbral de supresión para desgloses de servicios confidenciales
SUPRIMIDO = "<5"


def _suprimir(codigo_servicio: str, n: int):
    """En servicios confidenciales, un conteo pequeño se reporta como '<5'."""
    if codigo_servicio in SERVICIOS_CONFIDENCIALES and 0 < n < K_MINIMO:
        return SUPRIMIDO
    return n


def atenciones_por_servicio(desde=None, hasta=None) -> list[dict]:
    """Demanda por servicio. Psicología: solo el conteo, jamás el detalle."""
    from apps.expediente.models import Atencion

    qs = Atencion.objects.all()
    if desde:
        qs = qs.filter(fecha_hora__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_hora__date__lte=hasta)
    filas = (
        qs.values("servicio__codigo", "servicio__nombre")
        .annotate(total=Count("id"), pacientes=Count("expediente", distinct=True))
        .order_by("-total")
    )
    return [
        {
            "servicio": f["servicio__nombre"],
            # El total también se suprime bajo el umbral, y no por simetría:
            # los pacientes distintos nunca superan al total, así que un total
            # de 2 dice que los pacientes suprimidos son 1 o 2, y un total de 1
            # los revela exactamente. Publicar el total mientras se suprime el
            # otro dato dejaba reconstruirlo. Por encima del umbral no hay nada
            # que deducir y la demanda se ve completa.
            "total": _suprimir(f["servicio__codigo"], f["total"]),
            # "2 pacientes en psicología en la carrera X" señala a alguien.
            "pacientes": _suprimir(f["servicio__codigo"], f["pacientes"]),
        }
        for f in filas
    ]


def citas_indicadores(desde=None, hasta=None) -> dict:
    """Uso de la agenda: demanda, ausentismo y canal."""
    from apps.citas.models import Cita

    qs = Cita.objects.all()
    if desde:
        qs = qs.filter(fecha_hora__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_hora__date__lte=hasta)
    total = qs.count()
    por_estado = dict(qs.values_list("estado").annotate(n=Count("id")))
    atendidas = por_estado.get(Cita.Estado.ATENDIDA, 0)
    ausencias = por_estado.get(Cita.Estado.NO_ASISTIO, 0)
    finalizadas = atendidas + ausencias
    return {
        "total": total,
        "por_estado": por_estado,
        "por_canal": dict(qs.values_list("origen").annotate(n=Count("id"))),
        # El ausentismo se calcula sobre citas que llegaron a su hora
        # (atendida o no asistió), no sobre el total: contra reservas futuras
        # o canceladas a tiempo el indicador mentiría.
        "ausentismo_pct": round(ausencias * 100 / finalizadas, 1) if finalizadas else None,
    }


def derivaciones_indicadores() -> dict:
    """Flujo entre servicios. El destino confidencial aparece, su contenido no."""
    from apps.derivaciones.models import Derivacion

    filas = (
        Derivacion.objects.values("servicio_destino__codigo", "servicio_destino__nombre")
        .annotate(
            total=Count("id"),
            atendidas=Count("id", filter=Q(estado__in=["atendida", "retornada"])),
        )
        .order_by("-total")
    )
    return {
        "por_destino": [
            {
                "destino": f["servicio_destino__nombre"],
                # Mismo criterio que en atenciones_por_servicio: "1 derivación a
                # Psicología en el periodo" es un conteo pequeño sobre un
                # servicio confidencial, y cruzado con quién pasó por la Unidad
                # ese día señala igual que un nombre. El flujo entre servicios
                # se sigue viendo; lo que se vela es el tramo que identifica.
                "total": _suprimir(f["servicio_destino__codigo"], f["total"]),
                "atendidas": _suprimir(f["servicio_destino__codigo"], f["atendidas"]),
            }
            for f in filas
        ],
        "por_estado": dict(Derivacion.objects.values_list("estado").annotate(n=Count("id"))),
    }


def odontologia_cpod() -> dict:
    """
    CPO-D promedio: el indicador OMS que la Unidad reporta.

    El índice vive dentro del JSON `indices` (se congela al cerrar la
    atención), así que se promedia en Python: son pocas filas y el JSON no se
    agrega bien de forma portable entre SQLite y PostgreSQL.
    """
    from apps.odontologia.models import AtencionOdontologia

    valores = [
        fila["indices"]["cpod"]
        for fila in AtencionOdontologia.objects.exclude(indices={}).values("indices")
        if isinstance(fila["indices"], dict) and "cpod" in fila["indices"]
    ]
    return {
        "promedio": round(sum(valores) / len(valores), 2) if valores else 0,
        "atenciones_con_indice": len(valores),
    }


def psicopedagogia_impacto() -> dict:
    """Variación promedio del rendimiento en seguimientos con ambos promedios."""
    from apps.psicopedagogia.models import SeguimientoAcademico

    qs = SeguimientoAcademico.objects.filter(
        promedio_antes__isnull=False, promedio_despues__isnull=False
    )
    comparables = qs.count()
    if not comparables:
        return {"comparables": 0, "variacion_promedio": None}
    suma = sum(float(s.promedio_despues - s.promedio_antes) for s in qs)
    return {"comparables": comparables, "variacion_promedio": round(suma / comparables, 2)}


def laboratorio_indicadores() -> dict:
    from apps.laboratorio.models import OrdenLaboratorio

    return {
        "por_estado": dict(OrdenLaboratorio.objects.values_list("estado").annotate(n=Count("id"))),
    }


def becas_resumen() -> list[dict]:
    from apps.becas import services as becas_services
    from apps.core.models import PeriodoAcademico

    periodo = PeriodoAcademico.objects.filter(vigente=True).first()
    return becas_services.resumen_por_tipo(periodo) if periodo else []


def talleres_cobertura() -> dict:
    from apps.talleres import services as talleres_services

    return talleres_services.cobertura()


def tablero_general(desde=None, hasta=None) -> dict:
    """El tablero completo de la Dirección. Solo agregados; cero identidades."""
    return {
        "generado_en": timezone.now(),
        "atenciones": atenciones_por_servicio(desde, hasta),
        "citas": citas_indicadores(desde, hasta),
        "derivaciones": derivaciones_indicadores(),
        "odontologia": odontologia_cpod(),
        "psicopedagogia": psicopedagogia_impacto(),
        "laboratorio": laboratorio_indicadores(),
        "becas": becas_resumen(),
        "talleres": talleres_cobertura(),
    }
