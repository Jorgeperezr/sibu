"""
Que las cuentas sembradas sirvan de verdad: entran, y cada una llega a lo suyo.

Comprobar que una cuenta existe no basta. Ya pasó dos veces que existía y no
servía: la de administración no alcanzaba la carga de la base institucional
—rol PROFESIONAL contra una pantalla que pedía rol de administrador—, y antes
la contraseña sembrada no era la que se anunciaba. Estas pruebas recorren cada
cuenta y comprueban lo que debe poder hacer y lo que no.
"""

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.core.management.commands.datos_demo import ADMIN, CLAVE, PROFESIONALES, clave_de
from apps.expediente.models import Atencion
from apps.usuarios import rbac
from apps.usuarios.models import Rol, Usuario


@pytest.fixture
def sembrado(db, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def _entra(username, clave):
    cliente = Client()
    assert cliente.login(username=username, password=clave), f"no entra {username}"
    return cliente


# ------------------------------------------------------ todas las cuentas


@pytest.mark.django_db
def test_todas_las_cuentas_anunciadas_entran(sembrado):
    """
    Recorre lo que `make cuentas` promete y lo comprueba una por una. Una
    credencial anunciada que no funciona cuesta media hora de nadie.
    """
    credenciales = [(ADMIN["username"], ADMIN["clave"])]
    credenciales += [(p["usuario"], clave_de(p)) for p in PROFESIONALES]
    credenciales += [("administrador", CLAVE), ("director", CLAVE), ("estudiante", CLAVE)]

    for username, clave in credenciales:
        _entra(username, clave)


@pytest.mark.django_db
def test_no_hay_cuentas_duplicadas_ni_cedulas_repetidas(sembrado):
    usuarios = Usuario.objects.exclude(username="AnonymousUser")
    nombres = list(usuarios.values_list("username", flat=True))
    assert len(nombres) == len(set(nombres))

    cedulas = [c for c in usuarios.values_list("cedula", flat=True) if c]
    assert len(cedulas) == len(set(cedulas))


@pytest.mark.django_db
def test_cada_profesional_ve_solo_su_servicio(sembrado):
    """El comportamiento real, no una limitación del entorno de prueba."""
    for datos in PROFESIONALES:
        cuenta = Usuario.objects.get(username=datos["usuario"])
        servicios = list(cuenta.perfil.servicios.values_list("codigo", flat=True))
        assert servicios == [datos["servicio"]], f"{datos['usuario']} ve {servicios}"


# --------------------------------------------- la cuenta de administración


@pytest.mark.django_db
def test_la_cuenta_de_la_cedula_alcanza_la_carga_de_la_base(sembrado):
    """
    Lo que faltaba. La cuenta lleva rol PROFESIONAL para poder ver contenido
    clínico, y las pantallas de carga pedían rol de administrador: por rol
    nunca habría entrado. Ahora se comprueba el permiso, que es lo que de
    verdad expresa «puede cargar la base».
    """
    cliente = _entra(ADMIN["username"], ADMIN["clave"])
    for nombre in (
        "academico:padron",
        "academico:asistente",
        "academico:diccionario",
        "academico:plantilla",
    ):
        assert cliente.get(reverse(nombre)).status_code == 200, f"no alcanza {nombre}"


@pytest.mark.django_db
def test_la_cuenta_de_la_cedula_sigue_viendo_contenido_clinico(sembrado):
    """
    La otra mitad, y la razón de no hacerla administradora: `es_admin()` filtra
    las atenciones a cero. Las dos cosas a la vez son el motivo de que la
    autorización de la carga mire el permiso y no el rol.
    """
    cuenta = Usuario.objects.get(username=ADMIN["username"])
    assert cuenta.rol_principal == Rol.PROFESIONAL
    assert rbac.es_admin(cuenta) is False
    assert rbac.atenciones_visibles(cuenta, Atencion.objects.all()).exists()


@pytest.mark.django_db
def test_el_menu_le_ofrece_la_base_institucional(sembrado):
    """
    Que la vista se abra no basta: sin entrada de menú hay que teclear la URL.
    Y al revés: el menú no puede ofrecer un enlace que responda 403.
    """
    from apps.core.navegacion import modulos_visibles

    cuenta = Usuario.objects.get(username=ADMIN["username"])
    assert "Base institucional" in [m.etiqueta for m in modulos_visibles(cuenta)]


@pytest.mark.django_db
def test_un_profesional_corriente_no_alcanza_la_carga(sembrado):
    """
    Ampliar la autorización al permiso no puede volverla un colador: quien no
    lo tiene sigue fuera, y su menú no lo ofrece.
    """
    from apps.core.navegacion import modulos_visibles

    psicologo = Usuario.objects.get(username="jorge.perez")
    assert psicologo.has_perm("academico.add_cargainstitucional") is False
    assert "Base institucional" not in [m.etiqueta for m in modulos_visibles(psicologo)]

    cliente = _entra("jorge.perez", "jorge.perez")
    assert cliente.get(reverse("academico:padron")).status_code == 302
    assert cliente.get(reverse("academico:asistente")).status_code == 302


@pytest.mark.django_db
def test_el_autocompletado_responde_para_quien_atiende(sembrado):
    """
    Es lo que la carga viene a alimentar: si el padrón se llena y esto no
    responde, la carga no sirvió de nada.
    """
    cliente = _entra("jhoely.lalangui", "jhoely.lalangui")
    respuesta = cliente.get(reverse("academico:autocompletar"), {"q": "Jaramillo"})
    assert respuesta.status_code == 200
    assert "resultados" in respuesta.json()
