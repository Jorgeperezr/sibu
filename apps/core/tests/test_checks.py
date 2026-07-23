"""
Los checks de despliegue.

Una lista en prosa se lee una vez; estos corren en cada `check --deploy`. Estas
pruebas verifican que efectivamente detectan lo que dicen detectar.
"""

from pathlib import Path

import pytest
from django.core.checks import Error

from apps.core import checks


def _ids(resultados):
    return {r.id for r in resultados}


@pytest.mark.django_db
def test_en_desarrollo_no_molestan(settings):
    """Con DEBUG=True no se estorba al desarrollador."""
    settings.DEBUG = True
    settings.SECRET_KEY = "corta"
    settings.ALLOWED_HOSTS = ["*"]
    assert checks.comprobar_secretos(None) == []


@pytest.mark.django_db
def test_secret_key_de_desarrollo_en_produccion(settings):
    settings.DEBUG = False
    settings.SECRET_KEY = "django-insecure-abc"
    settings.ALLOWED_HOSTS = ["sibu.unl.edu.ec"]
    ids = _ids(checks.comprobar_secretos(None))
    assert "sibu.E001" in ids  # corta
    assert "sibu.E002" in ids  # parece de desarrollo


@pytest.mark.django_db
def test_allowed_hosts_comodin(settings):
    settings.DEBUG = False
    settings.SECRET_KEY = "x" * 60
    settings.ALLOWED_HOSTS = ["*"]
    assert "sibu.E003" in _ids(checks.comprobar_secretos(None))


def test_sqlite_en_produccion(settings):
    """
    La prueba fija el motor en lugar de heredarlo del entorno.

    Antes leía DATABASES tal como viniera: en un contenedor con
    DATABASE_URL=sqlite pasaba, y en Codespaces (PostgreSQL) fallaba, porque el
    check callaba con razón. Estaba comprobando la configuración de la máquina,
    no el comportamiento del check. Tampoco necesita base de datos: el check
    solo lee la cadena ENGINE.
    """
    settings.DEBUG = False
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
    assert "sibu.E010" in _ids(checks.comprobar_base_de_datos(None))


def test_postgresql_en_produccion_no_se_queja(settings):
    """El control positivo que faltaba."""
    settings.DEBUG = False
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "sibu"}}
    assert checks.comprobar_base_de_datos(None) == []


@pytest.mark.django_db
def test_falta_csrf_trusted_origins(settings):
    """El fallo de despliegue más común detrás de un proxy con HTTPS."""
    settings.DEBUG = False
    settings.SECURE_SSL_REDIRECT = True
    settings.CSRF_TRUSTED_ORIGINS = []
    assert "sibu.E020" in _ids(checks.comprobar_proxy_y_csrf(None))


@pytest.mark.django_db
def test_media_root_en_tmp(settings):
    settings.DEBUG = False
    settings.MEDIA_ROOT = "/tmp/media"  # nosec B108 - es el caso que se prueba
    assert "sibu.E031" in _ids(checks.comprobar_almacenamiento(None))


@pytest.mark.django_db
def test_las_dos_api_keys_de_firmaec_no_pueden_ser_iguales(settings):
    """Son credenciales de sentidos opuestos: si se filtra una, se filtran ambas."""
    settings.FIRMA_PROVIDER = "firmaec"
    settings.FIRMAEC_SERVICIO_URL = "https://impws.firmadigital.gob.ec/servicio"
    settings.FIRMAEC_SISTEMA = "sibu"
    settings.FIRMAEC_API_KEY = "la-misma"
    settings.FIRMAEC_CALLBACK_API_KEY = "la-misma"
    assert "sibu.E051" in _ids(checks.comprobar_firma(None))


@pytest.mark.django_db
def test_firma_deshabilitada_no_exige_nada(settings):
    settings.FIRMA_PROVIDER = "deshabilitada"
    settings.FIRMAEC_API_KEY = ""
    assert checks.comprobar_firma(None) == []


@pytest.mark.django_db
def test_se_avisa_si_psicologia_puede_salir_al_firmador(settings):
    """
    Aviso deliberado, no error: es una decisión que debe ser consciente y
    quedar a la vista en cada despliegue.
    """
    settings.FIRMAEC_DESCENTRALIZADO_PROPIO = True
    resultados = checks.comprobar_confidencialidad(None)
    assert "sibu.W060" in _ids(resultados)
    assert not any(isinstance(r, Error) for r in resultados)


@pytest.mark.django_db
def test_gdrive_sin_credenciales(settings):
    settings.TALLERES_ALMACEN = "gdrive"
    settings.GOOGLE_OAUTH = {"CLIENT_SECRETS_FILE": "", "SHARED_DRIVE_ID": ""}
    assert "sibu.E070" in _ids(checks.comprobar_talleres(None))


@pytest.mark.django_db
def test_una_configuracion_correcta_no_genera_errores(settings):
    """El control positivo: bien configurado, silencio."""
    settings.DEBUG = False
    settings.SECRET_KEY = "s" * 60
    settings.ALLOWED_HOSTS = ["sibu.unl.edu.ec"]
    settings.SECURE_SSL_REDIRECT = True
    settings.CSRF_TRUSTED_ORIGINS = ["https://sibu.unl.edu.ec"]
    # Ni tmp_path ni BASE_DIR sirven aquí: ambos pueden vivir bajo /tmp
    # (tmp_path siempre; BASE_DIR si el repositorio se clonó en /tmp, que es
    # justo lo que ocurre al verificar el paquete). El check acierta en
    # rechazarlos; la ruta de prueba tiene que ser persistente de verdad.
    media = Path.home() / "sibu_media_prueba"
    media.mkdir(parents=True, exist_ok=True)
    settings.MEDIA_ROOT = str(media)
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = "smtp.unl.edu.ec"
    settings.FIRMA_PROVIDER = "deshabilitada"
    settings.TALLERES_ALMACEN = "local"
    settings.FIRMAEC_DESCENTRALIZADO_PROPIO = False

    for fn in (
        checks.comprobar_secretos,
        checks.comprobar_proxy_y_csrf,
        checks.comprobar_almacenamiento,
        checks.comprobar_correo,
        checks.comprobar_firma,
        checks.comprobar_confidencialidad,
        checks.comprobar_talleres,
    ):
        assert fn(None) == [], f"{fn.__name__} se quejó de una config correcta"


def test_allowed_hosts_solo_de_desarrollo(settings):
    """
    Un ALLOWED_HOSTS heredado de desarrollo pasa E003 y E004, y sin embargo
    deja el sitio inservible: Django responde 400 por el dominio real.
    """
    settings.DEBUG = False
    settings.SECRET_KEY = "x" * 60
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
    assert "sibu.E005" in _ids(checks.comprobar_secretos(None))


def test_localhost_junto_al_dominio_real_es_legitimo(settings):
    """No se prohíbe localhost: una comprobación de salud local lo necesita."""
    settings.DEBUG = False
    settings.SECRET_KEY = "x" * 60
    settings.ALLOWED_HOSTS = ["sibu.unl.edu.ec", "localhost"]
    assert checks.comprobar_secretos(None) == []
