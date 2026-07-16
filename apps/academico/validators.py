"""Validaciones de datos institucionales (cédula ecuatoriana, correo, números)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def validar_cedula_ecuatoriana(cedula: str) -> bool:
    """
    Valida una cédula ecuatoriana (10 dígitos) con el algoritmo módulo 10.

    Reglas: los dos primeros dígitos son la provincia (01-24 o 30 para
    extranjeros), el tercero < 6 para personas naturales, y el último es el
    dígito verificador calculado sobre los 9 anteriores.
    """
    if cedula is None:
        return False
    cedula = str(cedula).strip()
    if len(cedula) != 10 or not cedula.isdigit():
        return False

    provincia = int(cedula[:2])
    if not (1 <= provincia <= 24 or provincia == 30):
        return False
    if int(cedula[2]) >= 6:
        return False

    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for coef, digito in zip(coeficientes, cedula[:9], strict=False):
        producto = coef * int(digito)
        total += producto - 9 if producto > 9 else producto
    verificador = (10 - (total % 10)) % 10
    return verificador == int(cedula[9])


def normalizar_cedula(cedula) -> str:
    """
    Limpia una cédula: elimina espacios y rellena con ceros a la izquierda
    si perdió el 0 inicial (Excel suele convertirla a número).
    """
    if cedula is None:
        return ""
    texto = str(cedula).strip().replace("-", "").replace(" ", "")
    # Excel suele eliminar el 0 inicial y convertir a número: 12345678.0
    if texto.endswith(".0"):
        texto = texto[:-2]
    if texto.isdigit() and len(texto) == 9:
        texto = "0" + texto
    return texto


def validar_correo_institucional(correo: str, dominio: str) -> bool:
    """Verifica que el correo pertenezca al dominio institucional (p. ej. unl.edu.ec)."""
    if not correo:
        return False
    correo = str(correo).strip().lower()
    return "@" in correo and correo.endswith("@" + dominio.lower())


def a_decimal(valor) -> Decimal:
    """Convierte un valor de ingreso/gasto a Decimal; devuelve 0 si no es numérico."""
    if valor in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(valor).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def a_fecha(valor):
    """Normaliza fechas de nacimiento en varios formatos comunes; None si falla."""
    if valor in (None, ""):
        return None
    if isinstance(valor, date | datetime):
        return valor.date() if isinstance(valor, datetime) else valor
    texto = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None
