"""Ajustes de desarrollo (Codespaces / macOS Intel). Nunca usar en producción."""

from .base import *  # noqa
from .base import BASE_DIR, env  # explícito: evita la ambigüedad del star-import
from .clave_dev import clave_de_desarrollo

DEBUG = True
ALLOWED_HOSTS = ["*"]  # Codespaces asigna hosts dinámicos


SECRET_KEY = env("SECRET_KEY", default="") or clave_de_desarrollo(BASE_DIR)

INSTALLED_APPS += ["debug_toolbar", "django_extensions"]  # noqa
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa
INTERNAL_IPS = ["127.0.0.1"]

# Correo por consola en desarrollo (no se envía nada real)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CSRF: Codespaces expone la app en *.app.github.dev
CSRF_TRUSTED_ORIGINS = ["https://*.app.github.dev", "https://*.githubpreview.dev"]

# En desarrollo se relajan controles que solo aplican tras HTTPS
AXES_ENABLED = env.bool("AXES_ENABLED", default=False)  # noqa
