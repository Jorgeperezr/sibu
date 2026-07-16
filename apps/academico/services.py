"""
Motor de carga de la ficha socioeconómica (asistente de 6 pasos, sección 7.2).

Flujo público:
    lector = LectorFicha(ruta, formato)
    columnas = lector.columnas()                 # paso 2: para el mapeo
    resultado = ProcesadorCarga(carga, mapeo).procesar(lector, aplicar=False)  # 3-4 (preview)
    ProcesadorCarga(carga, mapeo).procesar(lector, aplicar=True)               # 5 (aplicar)

Cada fila válida hace upsert de Persona + DatoAcademico, pre-puebla la
FichaSocioeconomica (origen=matrícula) y genera alertas hacia las bandejas de
Trabajo Social / Psicopedagogía / Psicología / Medicina (sección 12.7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from django.conf import settings
from django.db import transaction

from apps.core.models import Servicio
from apps.expediente.models import AlertaClinica, Expediente, Persona

from . import mapping, validators


# --------------------------------------------------------------------------
# Lectura del archivo
# --------------------------------------------------------------------------
class LectorFicha:
    """Lee un Excel/CSV y entrega filas como diccionarios normalizados."""

    def __init__(self, ruta: str, formato: str):
        self.ruta = ruta
        self.formato = formato
        self._df = None

    def _cargar(self):
        import pandas as pd  # import diferido: pandas es pesado

        if self._df is None:
            if self.formato == "csv":
                self._df = pd.read_csv(self.ruta, dtype=str, keep_default_na=False)
            else:
                self._df = pd.read_excel(self.ruta, dtype=str, keep_default_na=False)
            self._df.columns = [str(c).strip() for c in self._df.columns]
        return self._df

    def columnas(self) -> list[str]:
        return list(self._cargar().columns)

    def filas(self):
        df = self._cargar()
        for _, fila in df.iterrows():
            yield {k: (v if v != "" else None) for k, v in fila.to_dict().items()}

    def total(self) -> int:
        return len(self._cargar())


def hash_archivo(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            h.update(bloque)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Resultado del procesamiento
# --------------------------------------------------------------------------
@dataclass
class ResultadoCarga:
    total: int = 0
    altas: int = 0
    actualizaciones: int = 0
    errores: int = 0
    alertas_generadas: int = 0
    detalle_errores: list = field(default_factory=list)

    def as_dict(self):
        return {
            "total": self.total,
            "altas": self.altas,
            "actualizaciones": self.actualizaciones,
            "errores": self.errores,
            "alertas_generadas": self.alertas_generadas,
            "detalle_errores": self.detalle_errores[:200],  # cota para la bitácora
        }


# --------------------------------------------------------------------------
# Procesador
# --------------------------------------------------------------------------
class ProcesadorCarga:
    """Aplica el mapeo, valida y hace upsert. `aplicar=False` = solo previsualiza."""

    def __init__(self, carga, mapeo: dict | None = None):
        self.carga = carga
        self.periodo = carga.periodo
        # mapeo: alias_en_archivo -> columna_canonica. Por defecto, identidad.
        self.mapeo = mapeo or {}
        self.dominio = settings.SIBU["DOMINIO_CORREO_INSTITUCIONAL"]

    # -- utilidades de acceso a la fila usando el mapeo de alias --
    def _get(self, fila: dict, col_canonica: str):
        alias = self.mapeo.get(col_canonica, col_canonica)
        return fila.get(alias)

    def _subdict(self, fila: dict, columnas: list[str]) -> dict:
        return {c: self._get(fila, c) for c in columnas if self._get(fila, c) is not None}

    def procesar(self, lector: LectorFicha, aplicar: bool = False) -> ResultadoCarga:
        r = ResultadoCarga(total=lector.total())
        for indice, fila in enumerate(lector.filas(), start=2):  # fila 1 = encabezados
            try:
                self._procesar_fila(fila, r, aplicar)
            except Exception as exc:  # noqa: BLE001 - se reporta, no se aborta la carga
                r.errores += 1
                r.detalle_errores.append({"fila": indice, "error": str(exc)})
        return r

    def _procesar_fila(self, fila: dict, r: ResultadoCarga, aplicar: bool):
        cedula = validators.normalizar_cedula(self._get(fila, "cedula"))
        nombres = self._get(fila, "nombres")
        apellidos = self._get(fila, "apellidos")

        # Validaciones mínimas
        faltantes = [
            c
            for c in mapping.COLUMNAS_OBLIGATORIAS
            if not (self._get(fila, c) or (c == "cedula" and cedula))
        ]
        if faltantes:
            raise ValueError(f"Columnas obligatorias vacías: {', '.join(faltantes)}")
        if not validators.validar_cedula_ecuatoriana(cedula):
            raise ValueError(f"Cédula inválida: {cedula}")

        correo = self._get(fila, "email_institucional") or ""
        if correo and not validators.validar_correo_institucional(correo, self.dominio):
            # No es error bloqueante: se registra pero se continúa
            r.detalle_errores.append(
                {"cedula": cedula, "aviso": f"Correo no institucional: {correo}"}
            )

        if not aplicar:
            # Modo previsualización: solo cuenta alta/actualización sin escribir
            existe = Persona.objects.filter(cedula=cedula).exists()
            r.actualizaciones += 1 if existe else 0
            r.altas += 0 if existe else 1
            return

        with transaction.atomic():
            persona, creada = self._upsert_persona(fila, cedula, nombres, apellidos)
            self._upsert_dato_academico(fila, persona)
            expediente = self._asegurar_expediente(fila, persona)
            self._prepoblar_ficha(fila, expediente)
            r.alertas_generadas += self._generar_alertas(fila, expediente)
            r.altas += 1 if creada else 0
            r.actualizaciones += 0 if creada else 1

    # -- upserts --
    def _upsert_persona(self, fila, cedula, nombres, apellidos):
        defaults = {
            "nombres": nombres,
            "apellidos": apellidos,
            "tipo_documento": self._get(fila, "tipo_documento") or "cedula",
            "sexo": self._get(fila, "sexo") or "",
            "genero": self._get(fila, "genero") or "",
            "celular": self._get(fila, "celular") or "",
            "telefono": self._get(fila, "telefono") or "",
            "correo_institucional": self._get(fila, "email_institucional") or "",
            "tipo_vinculo": Persona.TipoVinculo.ESTUDIANTE,
            "fecha_nacimiento": validators.a_fecha(self._get(fila, "fecha_nacimiento")),
            "procedencia": self._subdict(fila, mapping.PERSONA_JSONB["procedencia"]),
            "residencia_actual": self._subdict(fila, mapping.PERSONA_JSONB["residencia_actual"]),
            "contacto_referencia": self._subdict(
                fila, mapping.PERSONA_JSONB["contacto_referencia"]
            ),
        }
        return Persona.objects.update_or_create(cedula=cedula, defaults=defaults)

    def _upsert_dato_academico(self, fila, persona):
        from .models import DatoAcademico

        defaults = {campo: (self._get(fila, col) or "") for col, campo in mapping.ACADEMICO.items()}
        defaults["carga"] = self.carga
        defaults["ficha_raw"] = {k: v for k, v in fila.items() if v is not None}
        DatoAcademico.objects.update_or_create(
            persona=persona, periodo=self.periodo, defaults=defaults
        )

    def _asegurar_expediente(self, fila, persona):
        expediente, _ = Expediente.objects.get_or_create(
            persona=persona,
            defaults={
                "numero_expediente": f"EXP-{persona.cedula}",
                "grupo_sanguineo": self._get(fila, "tipo_sangre") or "",
                "discapacidad_tipo": self._get(fila, "discapacidad_tipo") or "",
            },
        )
        return expediente

    def _prepoblar_ficha(self, fila, expediente):
        """Crea la FichaSocioeconomica (origen=matrícula) si no existe una vigente."""
        from apps.trabajo_social.models import FichaSocioeconomica

        if FichaSocioeconomica.objects.filter(expediente=expediente, vigente=True).exists():
            return  # ya existe (posiblemente verificada por Trabajo Social): no se sobrescribe

        ingresos = self._subdict(fila, mapping.FICHA_JSONB["ingresos"])
        egresos = self._subdict(fila, mapping.FICHA_JSONB["egresos"])
        FichaSocioeconomica.objects.create(
            expediente=expediente,
            origen=FichaSocioeconomica.Origen.MATRICULA,
            ingresos=ingresos,
            egresos=egresos,
            ingresos_totales=validators.a_decimal(self._get(fila, "ingreso_mensual")),
            egresos_totales=validators.a_decimal(self._get(fila, "gastos_mensual_familia")),
            vivienda_estudiante=self._subdict(fila, mapping.FICHA_JSONB["vivienda_estudiante"]),
            vivienda_familiar=self._subdict(fila, mapping.FICHA_JSONB["vivienda_familiar"]),
            convivencia=self._subdict(fila, mapping.FICHA_JSONB["convivencia"]),
            situacion_laboral=self._subdict(fila, mapping.FICHA_JSONB["situacion_laboral"]),
            salud_familiar=self._subdict(fila, mapping.FICHA_JSONB["salud_familiar"]),
        )

    def _generar_alertas(self, fila, expediente) -> int:
        """Crea alertas visibles en el expediente según REGLAS_ALERTA."""
        generadas = 0
        for columna, (tipo, _servicio, plantilla) in mapping.REGLAS_ALERTA.items():
            valor = self._get(fila, columna)
            if not valor or str(valor).strip().lower() in {"no", "0", "ninguno", "n/a"}:
                continue
            descripcion = plantilla.format(valor=valor)
            _, creada = AlertaClinica.objects.get_or_create(
                expediente=expediente,
                tipo=tipo,
                descripcion=descripcion,
                defaults={"activa": True},
            )
            generadas += 1 if creada else 0
        return generadas


def servicios_por_codigo():
    """Cache simple de servicios por código para el ruteo de alertas."""
    return {s.codigo: s for s in Servicio.objects.all()}
