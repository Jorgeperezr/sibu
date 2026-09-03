"""Ajustes de desarrollo (Codespaces / macOS Intel). Nunca usar en producción."""

from pathlib import Path

from .base import *  # noqa
from .base import BASE_DIR, env  # explícito: evita la ambigüedad del star-import

DEBUG = True
ALLOWED_HOSTS = ["*"]  # Codespaces asigna hosts dinámicos


def _clave_de_desarrollo() -> str:
    """
    Una SECRET_KEY utilizable en desarrollo, generada la primera vez.

    El README pedía `cp .env.example .env`, y ese ejemplo trae `SECRET_KEY=`
    vacía a propósito —es una plantilla de producción—. Con la clave vacía
    Django aborta al importar los ajustes con «The SECRET_KEY setting must not
    be empty»: no arrancaba nada, ni la pantalla de inicio de sesión. Aquí, en
    desarrollo, esa ausencia se resuelve sola.

    Se guarda en `.secret_key_dev` (ignorado por git) en vez de generarse en
    cada arranque: si cambiara, todas las sesiones y los tokens CSRF abiertos
    quedarían invalidados y el inicio de sesión fallaría en cada reinicio del
    servidor, que es justo el error que esto viene a quitar.

    prod.py NO hace nada de esto: allí una clave ausente debe seguir siendo un
    fallo ruidoso, porque una clave adivinable firma sesiones reales.
    """
    from django.core.management.utils import get_random_secret_key

    archivo = Path(BASE_DIR) / ".secret_key_dev"
    if archivo.exists():
        guardada = archivo.read_text(encoding="utf-8").strip()
        if guardada:
            return guardada
    generada = get_random_secret_key()
    try:
        archivo.write_text(generada, encoding="utf-8")
    except OSError:
        # Sistema de archivos de solo lectura: la clave sirve igual durante
        # este proceso, solo que las sesiones no sobrevivirán al reinicio.
        pass
    return generada


SECRET_KEY = env("SECRET_KEY", default="") or _clave_de_desarrollo()

INSTALLED_APPS += ["debug_toolbar", "django_extensions"]  # noqa
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa
INTERNAL_IPS = ["127.0.0.1"]

# Correo por consola en desarrollo (no se envía nada real)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CSRF: Codespaces expone la app en *.app.github.dev
CSRF_TRUSTED_ORIGINS = ["https://*.app.github.dev", "https://*.githubpreview.dev"]

# En desarrollo se relajan controles que solo aplican tras HTTPS
AXES_ENABLED = env.bool("AXES_ENABLED", default=False)  # noqa
