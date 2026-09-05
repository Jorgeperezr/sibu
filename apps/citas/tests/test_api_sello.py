"""
La API de citas listaba el padrón de pacientes de Psicología.

`CitaViewSet` llevaba `IsAuthenticated` y nada más: sin `get_queryset`, la
lista era la tabla entera. Y con `filterset_fields = ["servicio", ...]` no
hacía falta ni recorrerla:

    GET /api/v1/citas/?servicio=<id de psicología>

devolvía, por cada cita, el nombre completo del paciente, su cédula y el
motivo. A cualquiera con sesión iniciada, un estudiante incluido.

Es lo mismo que ya se corrigió en `mi_agenda` —«la agenda de Psicología, que
lista el nombre de cada paciente y el motivo de su cita»— y que quedó vivo por
la otra puerta. Estas pruebas cierran las dos: la lista y el detalle por id.
"""

from datetime import time, timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.citas import services
from apps.citas.models import Agenda
from apps.citas.tests.factories import _proximo_lunes
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"
MOTIVO_SELLADO = "Primera entrevista por crisis de ansiedad"


def _aware(fecha, hora):
    from datetime import datetime

    return timezone.make_aware(datetime.combine(fecha, hora), timezone.get_current_timezone())


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("medico_api", est["medicina"], est["salud"])
    psicologo, perfil_psico = crear_profesional("psicologo_api", est["psicologia"], est["psico"])
    estudiante = Usuario.objects.create_user(
        username="estudiante_api", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    ventanilla = Usuario.objects.create_user(
        username="ventanilla_api", password=CLAVE, rol_principal=Rol.ADMINISTRATIVO
    )
    for usuario in (medico, psicologo, estudiante, ventanilla):
        usuario.set_password(CLAVE)
        usuario.save()

    lunes = _proximo_lunes()
    for perfil, servicio in ((perfil_medico, est["medicina"]), (perfil_psico, est["psicologia"])):
        Agenda.objects.create(
            profesional=perfil,
            servicio=servicio,
            dia_semana=0,
            hora_inicio=time(8, 0),
            hora_fin=time(12, 0),
            duracion_turno_min=20,
            vigente_desde=lunes - timedelta(days=1),
        )
    exp = crear_expediente(cedula="1104567894")
    cita = services.reservar_cita(
        expediente=exp,
        servicio=est["medicina"],
        profesional=perfil_medico,
        fecha_hora=_aware(lunes, time(9, 0)),
        motivo="Control de presión",
    )
    cita_psico = services.reservar_cita(
        expediente=exp,
        servicio=est["psicologia"],
        profesional=perfil_psico,
        fecha_hora=_aware(lunes, time(10, 0)),
        motivo=MOTIVO_SELLADO,
    )
    return {
        "est": est,
        "medico": medico,
        "psicologo": psicologo,
        "estudiante": estudiante,
        "ventanilla": ventanilla,
        "cita": cita,
        "cita_psico": cita_psico,
    }


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


def _ids(respuesta):
    datos = respuesta.json()
    filas = datos["results"] if isinstance(datos, dict) and "results" in datos else datos
    return {f["id"] for f in filas}


# --------------------------------------------------------- el filtro por servicio


@pytest.mark.django_db
def test_filtrar_por_el_servicio_sellado_no_devuelve_su_padron(escenario):
    """El ataque de una sola petición: `?servicio=<psicología>`."""
    respuesta = _cliente(escenario["medico"]).get(
        "/api/v1/citas/", {"servicio": escenario["est"]["psicologia"].pk}
    )
    assert respuesta.status_code == 200
    assert _ids(respuesta) == set()
    assert MOTIVO_SELLADO not in respuesta.content.decode()


@pytest.mark.django_db
def test_la_lista_completa_tampoco_la_incluye(escenario):
    """Sin filtro, la tabla entera: el sello no puede depender del parámetro."""
    respuesta = _cliente(escenario["medico"]).get("/api/v1/citas/")
    assert escenario["cita_psico"].pk not in _ids(respuesta)
    assert escenario["cita"].pk in _ids(respuesta)


@pytest.mark.django_db
def test_el_detalle_por_id_devuelve_404(escenario):
    """Adivinar el id es la tercera puerta, y da igual que la lista esté bien."""
    respuesta = _cliente(escenario["medico"]).get(f"/api/v1/citas/{escenario['cita_psico'].pk}/")
    assert respuesta.status_code == 404


@pytest.mark.django_db
def test_psicologia_si_ve_las_suyas(escenario):
    """La corrección no puede dejar al servicio sin su propia agenda."""
    respuesta = _cliente(escenario["psicologo"]).get("/api/v1/citas/")
    assert escenario["cita_psico"].pk in _ids(respuesta)


# ------------------------------------------------------------ quién es personal


@pytest.mark.django_db
def test_un_estudiante_no_lista_citas_de_nadie(escenario):
    """
    Ni las de Psicología ni las de Medicina: el nombre y la cédula de quien
    tiene hora en la Unidad no son públicos para quien solo tiene una sesión.
    """
    respuesta = _cliente(escenario["estudiante"]).get("/api/v1/citas/")
    assert _ids(respuesta) == set()


@pytest.mark.django_db
def test_ventanilla_sigue_viendo_lo_que_agenda(escenario):
    """
    Quien reserva en ventanilla tiene rol ADMINISTRATIVO y ningún servicio
    asignado. Filtrar por servicio propio le habría dejado la pantalla vacía y
    roto el trabajo que esta API existe para hacer.
    """
    respuesta = _cliente(escenario["ventanilla"]).get("/api/v1/citas/")
    assert escenario["cita"].pk in _ids(respuesta)


@pytest.mark.django_db
def test_ventanilla_no_ve_las_del_servicio_sellado(escenario):
    """Que agende no le da derecho a leer quién va a Psicología."""
    respuesta = _cliente(escenario["ventanilla"]).get("/api/v1/citas/")
    assert escenario["cita_psico"].pk not in _ids(respuesta)
