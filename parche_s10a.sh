#!/usr/bin/env bash
# Parche 10a — corrige una prueba dependiente del entorno y el ruido del
# diagnóstico. Se aplica desde la raíz del repositorio.
set -euo pipefail

test -f apps/core/tests/test_checks.py || { echo "ERROR: ejecútelo desde la raíz del repo."; exit 1; }

python3 - <<'PY'
import sys
from pathlib import Path

# --- 1. La prueba debe FIJAR el motor, no heredarlo del entorno -------------
p = Path("apps/core/tests/test_checks.py")
s = p.read_text()
viejo = '''@pytest.mark.django_db
def test_sqlite_en_produccion(settings):
    settings.DEBUG = False
    assert "sibu.E010" in _ids(checks.comprobar_base_de_datos(None))'''
nuevo = '''def test_sqlite_en_produccion(settings):
    """
    La prueba fija el motor en lugar de heredarlo del entorno.

    Antes leía DATABASES tal como viniera: en un contenedor con
    DATABASE_URL=sqlite pasaba, y en Codespaces (PostgreSQL) fallaba, porque el
    check callaba con razón. Estaba comprobando la configuración de la máquina,
    no el comportamiento del check. Tampoco necesita base de datos: el check
    solo lee la cadena ENGINE.
    """
    settings.DEBUG = False
    settings.DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    }
    assert "sibu.E010" in _ids(checks.comprobar_base_de_datos(None))


def test_postgresql_en_produccion_no_se_queja(settings):
    """El control positivo que faltaba."""
    settings.DEBUG = False
    settings.DATABASES = {
        "default": {"ENGINE": "django.db.backends.postgresql", "NAME": "sibu"}
    }
    assert checks.comprobar_base_de_datos(None) == []'''
if viejo not in s:
    if "test_postgresql_en_produccion_no_se_queja" in s:
        print("   (1/3) la prueba ya estaba corregida; se omite")
    else:
        sys.exit("ERROR: no se encontró test_sqlite_en_produccion tal como se esperaba.")
else:
    p.write_text(s.replace(viejo, nuevo))
    print("   (1/3) prueba corregida: fija el motor y añade el control positivo")

# --- 2. El diagnóstico no debe alarmar con avisos de desarrollo -------------
p = Path("scripts/diagnostico.sh")
s = p.read_text()
viejo = '''python manage.py check --deploy 2>&1 | grep -E "sibu\\.[EW][0-9]+|security\\.[EW][0-9]+|System check" | head -25'''
nuevo = '''mod="${DJANGO_SETTINGS_MODULE:-config.settings.dev}"
echo "settings en uso: $mod"
case "$mod" in
  *prod*)
    python manage.py check --deploy 2>&1 | grep -E "sibu\\.[EW][0-9]+|security\\.[EW][0-9]+|System check" | head -25
    ;;
  *)
    echo "   Los checks de despliegue solo aplican con config.settings.prod."
    echo "   Bajo '$mod' permanecen en silencio A PROPÓSITO, y los avisos"
    echo "   security.W0xx que Django emite aquí describen la configuración de"
    echo "   desarrollo: son esperados y NO indican un problema."
    echo
    echo "   Para comprobar producción de verdad, con el .env real cargado:"
    echo "     DJANGO_SETTINGS_MODULE=config.settings.prod \\\\"
    echo "       python manage.py check --deploy"
    ;;
esac'''
# El centinela se comprueba ANTES que el ancla: el texto nuevo contiene el
# ancla dentro de la rama *prod*, así que buscarla primero re-aplicaría el
# parche sobre sí mismo y lo anidaría.
if "solo aplican con config.settings.prod" in s:
    print("   (2/3) el diagnóstico ya estaba corregido; se omite")
elif viejo in s:
    p.write_text(s.replace(viejo, nuevo))
    print("   (2/3) diagnóstico: distingue dev de prod en la sección 8")
else:
    sys.exit("ERROR: no se encontró la sección 8 de diagnostico.sh.")

# --- 3. El propio informe no debe ensuciar el árbol -------------------------
p = Path(".gitignore")
s = p.read_text()
if "diagnostico.txt" not in s:
    p.write_text(s.rstrip("\\n") + "\\n\\n# Informe local del script de diagnóstico\\ndiagnostico.txt\\n")
    print("   (3/3) .gitignore: diagnostico.txt")
else:
    print("   (3/3) .gitignore ya lo contempla; se omite")
PY
echo "Parche aplicado."
