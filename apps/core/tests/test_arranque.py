"""
El arranque en Codespaces.

Lo que se levantaba a mano dejaba dos formas de quedarse fuera del sistema, y
ninguna se explicaba sola:

- Copiar `.env.example` a `.env`, como pedía el README, dejaba `SECRET_KEY`
  vacía y Django abortaba al importar los ajustes: no arrancaba ni la pantalla
  de inicio de sesión.
- Arrancar sobre una base sin preparar levantaba el servidor y luego rechazaba
  cualquier usuario que se escribiera, porque no había ninguna cuenta creada.

Estas pruebas fijan lo que resuelve cada cosa. Siguiendo la disciplina de
`test_checks.py`, fijan lo que afirman en vez de heredarlo del entorno.
"""

import pytest
from django.core.management import call_command

from apps.core.models import Servicio
from apps.usuarios.models import Usuario

# --------------------------------------------------------- clave de desarrollo


# Se importa `clave_dev`, no `dev`: importar el módulo de ajustes de desarrollo
# tiene efectos —inserta el middleware del debug toolbar y dos apps en las
# listas que comparte con `base.py`—, y hacerlo desde una prueba alteraría los
# ajustes del resto de la suite. Por eso la función vive en un módulo aparte.
def test_la_clave_de_desarrollo_se_genera_si_no_hay_ninguna(tmp_path):
    """Sin esto, un `.env` con SECRET_KEY vacía impedía arrancar."""
    from config.settings.clave_dev import clave_de_desarrollo

    clave = clave_de_desarrollo(tmp_path)
    assert clave
    assert len(clave) >= 32


def test_la_clave_de_desarrollo_no_cambia_entre_arranques(tmp_path):
    """
    Si cambiara en cada arranque, las sesiones y los tokens CSRF abiertos
    quedarían invalidados y habría que volver a iniciar sesión tras cada
    reinicio del servidor: justo el error que esto viene a quitar.
    """
    from config.settings.clave_dev import clave_de_desarrollo

    assert clave_de_desarrollo(tmp_path) == clave_de_desarrollo(tmp_path)
    assert (tmp_path / ".secret_key_dev").exists()


def test_una_clave_guardada_vacia_se_regenera(tmp_path):
    """Un archivo truncado no puede dejar el sistema sin clave."""
    from config.settings.clave_dev import clave_de_desarrollo

    (tmp_path / ".secret_key_dev").write_text("   ", encoding="utf-8")
    assert clave_de_desarrollo(tmp_path).strip()


def test_la_clave_generada_no_se_versiona():
    """
    Una clave de firma en el repositorio deja de ser un secreto. Está en
    desarrollo, pero la costumbre de versionarla es la que luego llega a
    producción.
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[3]
    assert ".secret_key_dev" in (raiz / ".gitignore").read_text(encoding="utf-8")


# ------------------------------------------------------------------- preparar


@pytest.mark.django_db
def test_preparar_deja_la_base_utilizable(settings):
    """
    Estructura, permisos y al menos una cuenta con la que iniciar sesión: los
    tres motivos por los que el sistema parecía roto al primer arranque.
    """
    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    assert Servicio.objects.count() == 9
    assert Usuario.objects.exclude(username="AnonymousUser").exists()


@pytest.mark.django_db
def test_preparar_se_puede_repetir_sin_duplicar(settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    servicios = Servicio.objects.count()
    usuarios = Usuario.objects.count()
    call_command("preparar", verbosity=0)
    assert Servicio.objects.count() == servicios
    assert Usuario.objects.count() == usuarios


@pytest.mark.django_db
def test_preparar_sin_demo_no_siembra_pacientes():
    from apps.expediente.models import Persona

    call_command("preparar", "--sin-demo", verbosity=0)
    assert Servicio.objects.count() == 9
    assert not Persona.objects.exists()


@pytest.mark.django_db
def test_preparar_omite_la_demo_en_produccion(settings):
    """
    Los datos de demostración traen contraseñas conocidas y pacientes
    inventados: en un servidor real serían una puerta abierta con historias
    clínicas falsas dentro del expediente único.
    """
    from apps.expediente.models import Persona

    settings.DEBUG = False
    call_command("preparar", verbosity=0)
    assert Servicio.objects.count() == 9  # la estructura sí se prepara
    assert not Persona.objects.exists()


# -------------------------------------------------------------------- cuentas


@pytest.mark.django_db
def test_cuentas_lista_lo_que_existe(capsys, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    capsys.readouterr()  # descartar lo que imprimió la preparación
    call_command("cuentas")
    salida = capsys.readouterr().out
    assert "medico" in salida
    assert "sibu-demo-2026" in salida


@pytest.mark.django_db
def test_cuentas_no_anuncia_contrasenas_fuera_de_desarrollo(capsys, settings):
    """
    Con DEBUG=False la base no es de demostración: anunciar ahí unas
    contraseñas conocidas sería una invitación a probarlas.
    """
    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    capsys.readouterr()  # descartar lo que imprimió la preparación
    settings.DEBUG = False
    call_command("cuentas")
    salida = capsys.readouterr().out
    assert "medico" in salida
    assert "sibu-demo-2026" not in salida


@pytest.mark.django_db
def test_cuentas_avisa_cuando_no_hay_ninguna(capsys):
    Usuario.objects.all().delete()
    call_command("cuentas")
    assert "nadie puede iniciar sesión" in capsys.readouterr().out


@pytest.mark.django_db
def test_la_siembra_deja_una_cuenta_que_administra_sin_ver_lo_clinico(settings):
    """
    Separación de funciones, comprobada y no solo declarada.

    La cuenta con acceso a los nueve servicios tiene rol PROFESIONAL para poder
    ver atenciones; con solo esa, nadie llegaba a la base institucional, que
    pide ADMIN_GENERAL. Y darle ese rol la habría dejado ciega ante el contenido
    clínico. Son dos cuentas porque son dos funciones.
    """
    from apps.usuarios.models import Rol

    settings.DEBUG = True
    call_command("preparar", verbosity=0)

    administrador = Usuario.objects.get(username="administrador")
    assert administrador.rol_principal == Rol.ADMIN_GENERAL
    assert administrador.is_superuser is False

    from apps.core.management.commands.datos_demo import ADMIN

    con_servicios = Usuario.objects.get(username=ADMIN["username"])
    assert con_servicios.rol_principal == Rol.PROFESIONAL


@pytest.mark.django_db
def test_quien_administra_alcanza_el_padron_y_quien_atiende_no(settings, client):
    """
    Que el rol exista no basta: la pantalla tiene que abrirse. Y la de al lado,
    no: `medico` es profesional, y el padrón institucional no es suyo.
    """
    from django.urls import reverse

    settings.DEBUG = True
    call_command("preparar", verbosity=0)

    assert client.login(username="administrador", password="sibu-demo-2026")
    assert client.get(reverse("academico:padron")).status_code == 200

    assert client.login(username="medico", password="sibu-demo-2026")
    assert client.get(reverse("academico:padron")).status_code == 302


def test_ninguna_prueba_importa_los_ajustes_de_desarrollo():
    """
    Importar `config.settings.dev` desde una prueba inserta el middleware del
    debug toolbar y dos apps en las listas que ese módulo comparte con
    `base.py`. Bajo los ajustes de prueba esas listas son las que Django está
    usando, así que la importación altera la configuración del RESTO de la
    suite: las pruebas que vinieran después harían peticiones a través de un
    middleware que no les corresponde, y el fallo aparecería lejos de su causa.

    Esta prueba estuvo a punto de hacer justo eso. Se queda para que la
    siguiente no lo repita.
    """
    import re
    from pathlib import Path

    # Solo sentencias de importación, no la prosa: este mismo archivo nombra el
    # módulo al explicar por qué no debe importarse.
    patron = re.compile(
        r"^\s*(?:import\s+config\.settings\.dev|from\s+config\.settings(?:\.dev)?\s+import\s+(?:dev\b|\*))",
        re.MULTILINE,
    )
    raiz = Path(__file__).resolve().parents[2]
    culpables = [
        str(archivo.relative_to(raiz))
        for archivo in raiz.rglob("test_*.py")
        if patron.search(archivo.read_text(encoding="utf-8"))
    ]
    assert not culpables, f"importan los ajustes de desarrollo: {culpables}"


# ------------------------------------------------- la cuenta de administración


@pytest.mark.django_db
def test_la_cuenta_de_administracion_entra_con_su_cedula(settings, client):
    """
    Usuario y contraseña son la cédula: es como el modelo `Usuario` dice que se
    identifica una cuenta ("username = cédula o usuario institucional").
    """
    from apps.core.management.commands.datos_demo import ADMIN

    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    assert client.login(username=ADMIN["username"], password=ADMIN["clave"])
    assert Usuario.objects.get(username=ADMIN["username"]).cedula == ADMIN["cedula"]


@pytest.mark.django_db
def test_la_cuenta_de_administracion_sigue_viendo_contenido_clinico(settings):
    """
    Lo que impide convertirla en superusuario de verdad.

    `rbac.atenciones_visibles` devuelve `.none()` para cualquier administrador
    —`es_admin()` cubre `is_superuser` y `ADMIN_GENERAL`— por separación de
    funciones. Con cualquiera de los dos, esta cuenta abriría cada expediente y
    vería «0 atenciones»: lo contrario de poder probar el sistema. Por eso lleva
    rol PROFESIONAL con los nueve servicios, y el acceso a /admin/ va con
    permisos explícitos en vez de `is_superuser`.
    """
    from apps.core.management.commands.datos_demo import ADMIN
    from apps.expediente.models import Atencion
    from apps.usuarios import rbac
    from apps.usuarios.models import Rol

    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    cuenta = Usuario.objects.get(username=ADMIN["username"])

    assert cuenta.rol_principal == Rol.PROFESIONAL
    assert cuenta.is_superuser is False
    assert cuenta.is_staff is True  # entra a /admin/ por permisos explícitos
    assert cuenta.perfil.servicios.count() == 9

    visibles = rbac.atenciones_visibles(cuenta, Atencion.objects.all())
    assert visibles.exists(), "la cuenta de administración se quedó sin ver atenciones"


@pytest.mark.django_db
def test_la_cedula_de_la_cuenta_no_choca_al_resembrar(settings):
    """
    `Usuario.cedula` es única. Si una siembra anterior se la dejó a otra cuenta,
    volver a sembrar reventaría con IntegrityError en vez de reasignarla.
    """
    from apps.core.management.commands.datos_demo import ADMIN

    settings.DEBUG = True
    call_command("preparar", verbosity=0)
    intruso = Usuario.objects.create_user(username="intruso", password="clave-larga-12345")
    Usuario.objects.filter(pk=Usuario.objects.get(username=ADMIN["username"]).pk).update(
        cedula=None
    )
    intruso.cedula = ADMIN["cedula"]
    intruso.save(update_fields=["cedula"])

    call_command("datos_demo", verbosity=0)  # no debe reventar
    assert Usuario.objects.get(username=ADMIN["username"]).cedula == ADMIN["cedula"]
    intruso.refresh_from_db()
    assert intruso.cedula is None
