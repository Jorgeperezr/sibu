"""
Servicios del expediente único (informe 4.2, 5.2 M04).

Punto central para: vincular/crear el expediente de una persona por cédula,
construir el snapshot institucional que se congela en cada atención y consolidar
la línea de tiempo respetando el RBAC.
"""
from __future__ import annotations

from apps.academico.providers import get_provider

from .models import Expediente, Persona


def obtener_o_crear_expediente(persona: Persona, usuario=None) -> Expediente:
    """Devuelve el expediente de la persona; lo crea si no existe."""
    expediente, creado = Expediente.objects.get_or_create(
        persona=persona,
        defaults={"numero_expediente": f"EXP-{persona.cedula}", "creado_por": usuario},
    )
    return expediente


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
