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

from .models import AlertaClinica, Expediente, Persona


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


def registrar_alerta(
    expediente: Expediente, tipo: str, descripcion: str, *, usuario=None
) -> AlertaClinica:
    """
    Registra (o reactiva) una alerta clínica sobre el expediente.

    Antes solo la crearba la carga académica masiva o el panel de
    administración: no había manera de que un profesional marcara, por
    ejemplo, una gestación o una enfermedad catastrófica detectada en consulta.

    `AlertaClinica` es "visible en todo el expediente" por diseño —el modelo
    ya lo dice—: una alergia debe verla Farmacia, una NEE debe verla
    Psicopedagogía. No es contenido clínico narrativo, es una bandera, y por
    eso no compromete el sello de Psicología: lo que el sello protege es la
    evolución y el contenido de la atención, no la existencia de una bandera.

    Idempotente por (expediente, tipo, descripción): registrar la misma alerta
    dos veces la reactiva en vez de duplicarla.
    """
    tipo_valido = {c for c, _ in AlertaClinica.Tipo.choices}
    if tipo not in tipo_valido:
        raise ValidationError(f"Tipo de alerta no reconocido: {tipo}.")
    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise ValidationError("La alerta necesita una descripción.")

    alerta, creada = AlertaClinica.objects.get_or_create(
        expediente=expediente,
        tipo=tipo,
        descripcion=descripcion,
        defaults={"activa": True, "creado_por": usuario},
    )
    if not creada and not alerta.activa:
        alerta.activa = True
        alerta.save(update_fields=["activa"])
    return alerta


def desactivar_alerta(alerta: AlertaClinica) -> AlertaClinica:
    """Retira una alerta de la vista del expediente sin borrar su historial."""
    if alerta.activa:
        alerta.activa = False
        alerta.save(update_fields=["activa"])
    return alerta


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
