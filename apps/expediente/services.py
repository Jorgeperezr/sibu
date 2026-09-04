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


# ============================================================
# Alta en lote por cédulas
# ============================================================

# Lo que separa una cédula de la siguiente cuando se pegan varias: salto de
# línea, coma, punto y coma, tabulador o espacio. Se aceptan todas a la vez
# porque quien pega una lista la trae de donde la trae —una columna de Excel,
# un correo, un oficio— y no tiene por qué reformatearla.
SEPARADORES = "\n\r\t,;. "

# Cota del lote. No es un capricho: cada cédula consulta el padrón y puede
# abrir un expediente, y una petición web que haga eso diez mil veces se cae
# por tiempo dejando el trabajo a medias y sin decir por dónde iba.
MAXIMO_POR_LOTE = 300


def separar_cedulas(texto: str) -> list[str]:
    """
    Parte un bloque de texto en cédulas, conservando el orden y sin repetir.

    Se conserva el orden porque el informe de resultados se lee contra la lista
    que la persona pegó: reordenarlo obligaría a buscar cada línea. Y no se
    repiten porque la misma cédula dos veces es un error de copiado, no una
    orden de registrar a alguien dos veces.
    """
    if not texto:
        return []
    for separador in SEPARADORES:
        texto = texto.replace(separador, "\n")
    vistas: set[str] = set()
    ordenadas = []
    for parte in texto.split("\n"):
        parte = parte.strip()
        if parte and parte not in vistas:
            vistas.add(parte)
            ordenadas.append(parte)
    return ordenadas


def registrar_lote_de_cedulas(texto: str, usuario=None) -> dict:
    """
    Resuelve una lista de cédulas de una vez y devuelve qué pasó con cada una.

    Cada cédula se procesa por separado y a propósito: una mal digitada en
    medio de doscientas no puede tumbar el lote entero ni dejarlo a medias sin
    decir dónde se cortó. Por eso aquí NO hay una transacción que envuelva todo.

    Se admiten nueve o diez dígitos. Con nueve se antepone el cero que Excel
    suele comerse al tratar la cédula como número —lo hace `normalizar_cedula`,
    que ya existía—, y el resultado se informa para que quien lo lea vea en qué
    se convirtió lo que pegó.

    Estados posibles por cédula:

    - `abierto`     el expediente se creó ahora.
    - `existente`   ya lo tenía; no se toca nada.
    - `invalida`    no pasa el módulo 10 ecuatoriano.
    - `desconocida` válida, pero no está en la base institucional.

    Una cédula desconocida NO se registra con nombre en blanco. Un expediente
    sin nombre no identifica a nadie y ensucia el padrón para siempre; se
    informa con un enlace para completar el alta a mano. Es la misma regla de
    siempre: ausencia de dato no es prueba de ausencia, y tampoco licencia para
    inventarlo.
    """
    from apps.academico.validators import validar_cedula_ecuatoriana

    entradas = separar_cedulas(texto)
    if not entradas:
        raise ValidationError("No se reconoció ninguna cédula en lo que escribió.")
    if len(entradas) > MAXIMO_POR_LOTE:
        raise ValidationError(
            f"El lote trae {len(entradas)} cédulas y el máximo por tanda es "
            f"{MAXIMO_POR_LOTE}. Divídalo y repita."
        )

    filas = []
    for original in entradas:
        cedula = normalizar_cedula(original)
        fila = {"original": original, "cedula": cedula, "expediente": None, "persona": None}

        if not validar_cedula_ecuatoriana(cedula):
            fila["estado"] = "invalida"
            fila["detalle"] = (
                "No pasa el módulo 10 ecuatoriano."
                if cedula.isdigit()
                else "No es un número de cédula."
            )
            filas.append(fila)
            continue

        # Antes de resolver, porque `resolver_por_cedula` crea el expediente si
        # falta: preguntar después ya no distinguiría lo que había de lo nuevo.
        ya_tenia = Expediente.objects.filter(persona__cedula=cedula).exists()
        resultado = resolver_por_cedula(cedula, usuario=usuario)

        if resultado is None:
            fila["estado"] = "desconocida"
            fila["detalle"] = "No consta en la base institucional; regístrela a mano."
        else:
            fila["persona"] = resultado["persona"]
            fila["expediente"] = resultado["expediente"]
            fila["estado"] = "existente" if ya_tenia else "abierto"
            fila["detalle"] = ""
        filas.append(fila)

    resumen = {estado: 0 for estado in ("abierto", "existente", "invalida", "desconocida")}
    for fila in filas:
        resumen[fila["estado"]] += 1

    # Fuera de cualquier bloque atómico y después del trabajo, no antes:
    # registrar y luego abortar dentro de la misma transacción revierte el
    # propio registro. Ya nos costó caro dos veces (firma, portal).
    if usuario is not None and usuario.is_authenticated:
        from apps.auditoria.models import LogAuditoria

        LogAuditoria.objects.create(
            usuario=usuario,
            rol_activo=getattr(usuario, "rol_principal", ""),
            accion=LogAuditoria.Accion.CREATE,
            modulo="expediente",
            entidad="Expediente",
            entidad_id="lote",
            detalle={"total": len(filas), **resumen},
        )

    return {"filas": filas, "resumen": resumen, "total": len(filas)}
