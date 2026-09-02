"""
Servicios del expediente único (informe 4.2, 5.2 M04).

Punto central para: vincular/crear el expediente de una persona por cédula,
construir el snapshot institucional que se congela en cada atención y consolidar
la línea de tiempo respetando el RBAC.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academico.providers import get_provider
from apps.academico.validators import normalizar_cedula

from .models import Expediente, Persona


def obtener_o_crear_expediente(persona: Persona, usuario=None) -> Expediente:
    """Devuelve el expediente de la persona; lo crea si no existe."""
    expediente, creado = Expediente.objects.get_or_create(
        persona=persona,
        defaults={"numero_expediente": f"EXP-{persona.cedula}", "creado_por": usuario},
    )
    return expediente


def registrar_persona(datos: dict, usuario=None) -> Expediente:
    """
    Da de alta a una persona y abre su expediente.

    Es la salida al callejón que dejaba la búsqueda: cuando una cédula no está
    ni en la base local ni en la institucional, la pantalla ofrecía registrarla
    como externa pero no había por dónde hacerlo.

    No valida la cédula aquí: `Persona.save()` aplica el módulo 10 sobre los
    documentos de tipo cédula, así que la comprobación vive en un solo sitio.
    """
    cedula = normalizar_cedula(datos.get("cedula", ""))
    if Persona.objects.filter(cedula=cedula).exists():
        raise ValidationError(f"Ya existe una persona registrada con la cédula {cedula}.")

    if not (datos.get("nombres") or "").strip() or not (datos.get("apellidos") or "").strip():
        raise ValidationError("Nombres y apellidos son obligatorios.")

    with transaction.atomic():
        persona = Persona.objects.create(
            cedula=cedula,
            tipo_documento=datos.get("tipo_documento") or "cedula",
            nombres=datos["nombres"].strip(),
            apellidos=datos["apellidos"].strip(),
            fecha_nacimiento=datos.get("fecha_nacimiento") or None,
            sexo=datos.get("sexo", ""),
            tipo_vinculo=datos.get("tipo_vinculo") or Persona.TipoVinculo.EXTERNO,
            correo_institucional=datos.get("correo_institucional", ""),
            correo_personal=datos.get("correo_personal", ""),
            telefono=datos.get("telefono", ""),
            celular=datos.get("celular", ""),
            creado_por=usuario,
        )
        return obtener_o_crear_expediente(persona, usuario)


def resolver_por_cedula(cedula: str, usuario=None):
    """
    Resuelve una cédula a (persona, expediente, datos_institucionales).

    Si la persona no está en la base local, consulta el proveedor académico
    (fase 1: réplica de la ficha; fase 2: SGA). Devuelve None si no existe en
    ninguna fuente (candidata a registro manual como externo).
    """
    persona = Persona.objects.filter(cedula=cedula).first()
    datos = get_provider().consultar_persona(cedula)

    if persona is None and datos is None:
        return None

    if persona is None and datos is not None:
        persona = Persona.objects.create(
            cedula=datos["cedula"],
            nombres=datos.get("nombres", ""),
            apellidos=datos.get("apellidos", ""),
            tipo_vinculo=datos.get("tipo_vinculo", Persona.TipoVinculo.EXTERNO),
            correo_institucional=datos.get("email_institucional", ""),
            creado_por=usuario,
        )

    expediente = obtener_o_crear_expediente(persona, usuario) if persona else None
    return {"persona": persona, "expediente": expediente, "institucional": datos}


def construir_snapshot(persona: Persona) -> dict:
    """
    Congela los datos institucionales vigentes para guardarlos en la atención
    (informe 7.5): así los reportes históricos reflejan la carrera/período del
    momento de la atención aunque luego cambien.
    """
    datos = get_provider().consultar_persona(persona.cedula) or {}
    return {
        "facultad": datos.get("facultad", ""),
        "carrera": datos.get("carrera", ""),
        "ciclo": datos.get("ciclo", ""),
        "modalidad": datos.get("modalidad", ""),
        "jornada": datos.get("jornada", ""),
        "estado": datos.get("estado", ""),
        "periodo": datos.get("periodo", ""),
        "tipo_vinculo": persona.tipo_vinculo,
    }
