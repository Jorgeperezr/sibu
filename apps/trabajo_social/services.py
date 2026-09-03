"""
Lógica de negocio de Trabajo Social (informe 6.8, 7.3).

La ficha socioeconómica se PRE-PUEBLA desde la ficha de matrícula y el
profesional la verifica. Nunca se sobrescribe: cada verificación crea una
versión nueva y la anterior queda como histórico. Esto importa porque el
puntaje socioeconómico decide asignación de becas: hay que poder auditar con
qué datos se decidió en cada momento.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Atencion, Expediente
from apps.expediente.services import construir_snapshot
from apps.usuarios.models import PerfilProfesional

from .models import FichaSocioeconomica, VisitaDomiciliaria

# Estratos por ingreso per cápita respecto al salario básico unificado (SBU).
# Ecuador 2026: SBU = 470 USD. Parametrizable desde ParametroSistema.
SBU_DEFECTO = Decimal("470.00")


def _sbu() -> Decimal:
    from apps.core.models import ParametroSistema

    param = ParametroSistema.objects.filter(clave="SBU").first()
    return Decimal(str(param.valor)) if param else SBU_DEFECTO


def ficha_vigente(expediente: Expediente) -> FichaSocioeconomica | None:
    """
    Versión vigente de la ficha socioeconómica del expediente.

    La restricción `uniq_ficha_socio_vigente_por_expediente` garantiza que hay
    como mucho una, así que el `.first()` es inequívoco.
    """
    return FichaSocioeconomica.objects.filter(expediente=expediente, vigente=True).first()


@transaction.atomic
def prepoblar_desde_matricula(expediente: Expediente, usuario=None) -> FichaSocioeconomica:
    """
    Crea la ficha v1 con los datos que el estudiante declaró en matrícula.

    No inventa datos: solo copia lo que existe en la ficha socioeconómica de
    matrícula (informe 7.3). Queda marcada como `origen=matricula` para que se
    distinga de lo verificado por el profesional.
    """
    if ficha_vigente(expediente) is not None:
        raise ValidationError(
            "El expediente ya tiene una ficha socioeconómica vigente. "
            "Use verificar_ficha() para registrar cambios."
        )
    persona = expediente.persona
    return FichaSocioeconomica.objects.create(
        expediente=expediente,
        version=1,
        vigente=True,
        origen=FichaSocioeconomica.Origen.MATRICULA,
        vivienda_estudiante=persona.residencia_actual or {},
        vivienda_familiar=persona.procedencia or {},
        convivencia={"contacto_referencia": persona.contacto_referencia or {}},
        creado_por=usuario,
    )


def calcular_totales(ingresos: dict, egresos: dict) -> tuple[Decimal, Decimal]:
    """Suma los valores numéricos de los diccionarios de ingresos y egresos."""

    def _suma(d: dict) -> Decimal:
        total = Decimal("0")
        for valor in (d or {}).values():
            try:
                total += Decimal(str(valor))
            except (TypeError, ValueError, ArithmeticError):
                continue  # las entradas no numéricas son descriptivas, no montos
        return total

    return _suma(ingresos), _suma(egresos)


def calcular_puntaje(ficha: FichaSocioeconomica) -> tuple[Decimal, str]:
    """
    Calcula el ingreso per cápita del hogar y su estrato.

    El puntaje es el ingreso per cápita expresado en SBU. Se usa como insumo
    para becas (fase 1: solo informativo; la asignación la decide el comité).
    """
    ingresos, _ = calcular_totales(ficha.ingresos, ficha.egresos)
    miembros = int((ficha.convivencia or {}).get("numero_miembros", 1) or 1)
    if miembros < 1:
        miembros = 1

    per_capita = ingresos / Decimal(miembros)
    puntaje = (per_capita / _sbu()).quantize(Decimal("0.01"))

    if puntaje < Decimal("0.5"):
        estrato = "Extrema vulnerabilidad"
    elif puntaje < Decimal("1.0"):
        estrato = "Vulnerabilidad alta"
    elif puntaje < Decimal("2.0"):
        estrato = "Vulnerabilidad media"
    else:
        estrato = "Sin vulnerabilidad económica"
    return puntaje, estrato


@transaction.atomic
def verificar_ficha(
    expediente: Expediente, datos: dict, *, profesional: PerfilProfesional, usuario=None
) -> FichaSocioeconomica:
    """
    Registra una versión verificada de la ficha.

    La versión anterior NO se borra ni se edita: se marca como no vigente y la
    nueva queda como v(n+1). Así se puede auditar con qué datos se otorgó una
    beca en cualquier momento del pasado.
    """
    # Bloquear las fichas del expediente antes de leer la vigente: dos
    # verificaciones simultáneas leían la misma `actual`, ambas creaban la
    # v(n+1) y ambas desmarcaban la v(n). Sin el bloqueo, la restricción de
    # vigencia única convertiría esa carrera en un IntegrityError en la cara
    # del usuario en vez de serializarla.
    list(FichaSocioeconomica.objects.select_for_update().filter(expediente=expediente))

    actual = ficha_vigente(expediente)
    version = (actual.version + 1) if actual else 1

    campos = {
        "ingresos",
        "egresos",
        "vivienda_estudiante",
        "vivienda_familiar",
        "convivencia",
        "situacion_laboral",
        "salud_familiar",
    }
    valores = {k: v for k, v in datos.items() if k in campos}
    if actual is not None:
        # Arrastrar lo no modificado desde la versión anterior
        for campo in campos:
            valores.setdefault(campo, getattr(actual, campo) or {})

    # Desmarcar la anterior ANTES de crear la nueva. El orden importa por dos
    # razones: la restricción de vigencia única rechazaría la nueva mientras la
    # vieja siga vigente, y hacerlo al revés —como estaba— dejaba dos vigentes
    # si algo fallaba entre ambos pasos.
    if actual is not None:
        actual.vigente = False
        actual.save(update_fields=["vigente", "actualizado_en"])

    nueva = FichaSocioeconomica(
        expediente=expediente,
        version=version,
        vigente=True,
        origen=FichaSocioeconomica.Origen.VERIFICADA,
        creado_por=usuario,
        **valores,
    )
    nueva.ingresos_totales, nueva.egresos_totales = calcular_totales(nueva.ingresos, nueva.egresos)
    nueva.save()
    nueva.puntaje, nueva.estrato = calcular_puntaje(nueva)
    nueva.save(update_fields=["puntaje", "estrato"])
    return nueva


def historial_fichas(expediente: Expediente):
    """Todas las versiones de la ficha, de la más reciente a la más antigua."""
    return FichaSocioeconomica.objects.filter(expediente=expediente).order_by("-version")


@transaction.atomic
def crear_atencion_ts(
    *, expediente: Expediente, profesional: PerfilProfesional, motivo: str = "", usuario=None
) -> Atencion:
    """Abre una atención de Trabajo Social."""
    try:
        servicio = Servicio.objects.get(codigo="trabajo-social")
    except Servicio.DoesNotExist as exc:
        raise ValidationError("El servicio 'trabajo-social' no está configurado.") from exc

    return Atencion.objects.create(
        expediente=expediente,
        servicio=servicio,
        profesional=profesional,
        fecha_hora=timezone.now(),
        motivo_consulta=motivo,
        snapshot_academico=construir_snapshot(expediente.persona),
        creado_por=usuario,
    )


def registrar_visita(
    atencion: Atencion,
    *,
    fecha=None,
    condiciones: dict | None = None,
    georreferencia: dict | None = None,
    observaciones: str = "",
) -> VisitaDomiciliaria:
    """Registra una visita domiciliaria con las condiciones verificadas in situ."""
    if atencion.inmutable:
        raise ValidationError("No se pueden registrar visitas en una atención firmada.")
    fecha = fecha or timezone.localdate()
    if fecha > timezone.localdate():
        raise ValidationError("No se puede registrar una visita con fecha futura.")

    return VisitaDomiciliaria.objects.create(
        atencion=atencion,
        fecha=fecha,
        condiciones_verificadas=condiciones or {},
        georreferencia=georreferencia or {},
        observaciones=observaciones,
    )
