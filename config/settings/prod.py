"""Ajustes de producción. Endurecimiento de seguridad activo."""
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from .base import *  # noqa

DEBUG = False

# --- HTTPS / cabeceras de seguridad ---
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 15  # 15 min de inactividad en estaciones clínicas
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Content Security Policy (django-csp) ---
MIDDLEWARE.insert(1, "csp.middleware.CSPMiddleware")  # noqa
CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "https://cdn.jsdelivr.net")
CSP_SCRIPT_SRC = ("'self'", "https://cdn.jsdelivr.net")
CSP_IMG_SRC = ("'self'", "data:")

# --- Archivos estáticos servidos por WhiteNoise ---
STORAGES = {  # noqa
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa

# --- Correo institucional (SMTP UNL / Google Workspace) ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST")  # noqa
EMAIL_PORT = env.int("EMAIL_PORT", default=587)  # noqa
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER")  # noqa
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")  # noqa
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="bienestar@unl.edu.ec")  # noqa

# --- Observabilidad ---
if env("SENTRY_DSN", default=""):  # noqa
    sentry_sdk.init(dsn=env("SENTRY_DSN"), integrations=[DjangoIntegration()],  # noqa
                    traces_sample_rate=0.1, send_default_pii=False)
