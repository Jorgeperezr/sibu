"""
Alta de personas desde la web.

Sin esta pantalla no se podía registrar a nadie sin abrir el shell, y todos los
módulos parten de un expediente existente: era el tapón de todo el sistema. La
búsqueda incluso ofrecía "puede registrarla como persona externa" sin dar por
dónde hacerlo.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client

from apps.expediente.models import Expediente, Persona
from apps.expediente.services import registrar_persona
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    u, _ = crear_profesional("medico_alta", est["medicina"], est["salud"])
    u.set_password(CLAVE)
    u.save()
    return {"est": est, "u": u}


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_registrar_persona_abre_su_expediente(escenario):
    exp = registrar_persona(
        {
            "cedula": "1104567894",
            "nombres": "Ana",
            "apellidos": "Prueba",
            "tipo_vinculo": Persona.TipoVinculo.ESTUDIANTE,
        },
        usuario=escenario["u"],
    )
    assert exp.numero_expediente == "EXP-1104567894"
    assert exp.persona.nombre_completo == "Prueba Ana"


@pytest.mark.django_db
def test_no_se_registra_dos_veces_la_misma_cedula(escenario):
    datos = {"cedula": "1104567894", "nombres": "Ana", "apellidos": "Prueba"}
    registrar_persona(datos, usuario=escenario["u"])
    with pytest.raises(ValidationError, match="Ya existe"):
        registrar_persona(datos, usuario=escenario["u"])


@pytest.mark.django_db
def test_una_cedula_invalida_no_crea_nada(escenario):
    """El módulo 10 lo aplica `Persona.save()`; aquí se comprueba que corta antes
    de dejar un expediente huérfano."""
    with pytest.raises(ValidationError):
        registrar_persona(
            {"cedula": "1104567890", "nombres": "Ana", "apellidos": "Prueba"},
            usuario=escenario["u"],
        )
    assert not Persona.objects.filter(cedula="1104567890").exists()
    assert not Expediente.objects.exists()


@pytest.mark.django_db
def test_sin_nombres_no_se_registra(escenario):
    with pytest.raises(ValidationError, match="obligatorios"):
        registrar_persona({"cedula": "1104567894", "nombres": " ", "apellidos": "Prueba"})


@pytest.mark.django_db
def test_un_externo_con_pasaporte_se_registra(escenario):
    exp = registrar_persona(
        {
            "cedula": "X998877",
            "tipo_documento": "pasaporte",
            "nombres": "Jane",
            "apellidos": "Doe",
            "tipo_vinculo": Persona.TipoVinculo.EXTERNO,
        }
    )
    assert exp.pk is not None


# ---------------------------------------------------------------------- web


@pytest.mark.django_db
def test_el_formulario_da_de_alta_y_redirige_al_expediente(escenario):
    c = Client()
    c.login(username="medico_alta", password=CLAVE)
    r = c.post(
        "/expediente/nuevo/",
        {
            "cedula": "1104567894",
            "tipo_documento": "cedula",
            "nombres": "Ana",
            "apellidos": "Prueba",
            "tipo_vinculo": Persona.TipoVinculo.ESTUDIANTE,
        },
    )
    exp = Expediente.objects.get()
    assert r.status_code == 302
    assert r.url == f"/expediente/{exp.pk}/"


@pytest.mark.django_db
def test_el_formulario_avisa_de_la_cedula_invalida_sin_crear_nada(escenario):
    c = Client()
    c.login(username="medico_alta", password=CLAVE)
    r = c.post(
        "/expediente/nuevo/",
        {"cedula": "1104567890", "nombres": "Ana", "apellidos": "Prueba"},
    )
    assert r.status_code == 200  # se queda en el formulario, no revienta
    assert "no es válida" in r.content.decode()
    assert not Expediente.objects.exists()


@pytest.mark.django_db
def test_un_usuario_del_portal_no_registra_expedientes(escenario):
    """El portal es para consultar lo propio, no para dar de alta a nadie."""
    Usuario.objects.create_user(
        username="estu_alta", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    c = Client()
    c.login(username="estu_alta", password=CLAVE)
    r = c.post(
        "/expediente/nuevo/",
        {"cedula": "1104567894", "nombres": "Ana", "apellidos": "Prueba"},
    )
    assert r.status_code == 302
    assert not Expediente.objects.exists()
