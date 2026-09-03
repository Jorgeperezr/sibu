"""
Informe demográfico de un servicio.

Distinto del tablero de la Dirección: aquí no hay K_MÍNIMO porque el
profesional que lo genera ya ve el contenido clínico completo de esas
atenciones, una por una. Lo que se prueba es que las ocho columnas pedidas
cuenten lo correcto, que cada profesional vea solo lo suyo, y que el conteo
sea por atención y no por paciente distinto.

Embarazo, lactancia, enfermedad catastrófica y necesidad educativa especial no
tenían dónde vivir en el sistema antes de hoy: se resuelven con los tipos de
`AlertaClinica` añadidos en el mismo commit.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.expediente.models import AlertaClinica, Atencion
from apps.expediente.services import registrar_alerta
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.reportes import services
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil_medico = crear_profesional("medico_informe", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()

    exp1 = crear_expediente(cedula="1104567894")
    exp1.persona.sexo = "mujer"
    exp1.persona.genero = "femenino"
    exp1.persona.etnia = "mestiza"
    exp1.persona.save()
    registrar_alerta(exp1, AlertaClinica.Tipo.GESTACION, "Gestación de 20 semanas")

    exp2 = crear_expediente(cedula="1712345675")
    exp2.persona.sexo = "hombre"
    exp2.persona.save()
    exp2.discapacidad_tipo = "física"
    exp2.discapacidad_porcentaje = 30
    exp2.save()

    for exp in (exp1, exp1, exp2):  # exp1 se atiende dos veces, exp2 una.
        Atencion.objects.create(
            expediente=exp,
            servicio=est["medicina"],
            profesional=perfil_medico,
            fecha_hora=timezone.now(),
        )
    return {"est": est, "medico": medico, "exp1": exp1, "exp2": exp2}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_cuenta_por_atencion_no_por_paciente(escenario):
    datos = services.informe_demografico(escenario["est"]["medicina"])
    assert datos["total_atenciones"] == 3


@pytest.mark.django_db
def test_sexo_genero_y_etnia_se_desglosan(escenario):
    datos = services.informe_demografico(escenario["est"]["medicina"])
    por_sexo = {f["etiqueta"]: f["total"] for f in datos["sexo"]}
    assert por_sexo == {"mujer": 2, "hombre": 1}
    por_genero = {f["etiqueta"]: f["total"] for f in datos["genero"]}
    assert por_genero == {"femenino": 2, services.SIN_DATO: 1}
    por_etnia = {f["etiqueta"]: f["total"] for f in datos["etnia"]}
    assert por_etnia == {"mestiza": 2, services.SIN_DATO: 1}


@pytest.mark.django_db
def test_discapacidad_es_si_o_no(escenario):
    datos = services.informe_demografico(escenario["est"]["medicina"])
    por_discapacidad = {f["etiqueta"]: f["total"] for f in datos["discapacidad"]}
    assert por_discapacidad == {"Sin discapacidad": 2, "Con discapacidad": 1}


@pytest.mark.django_db
def test_embarazo_cuenta_las_atenciones_con_la_alerta_activa(escenario):
    datos = services.informe_demografico(escenario["est"]["medicina"])
    assert datos["embarazo"] == 2  # las dos atenciones de exp1
    assert datos["lactancia"] == 0
    assert datos["enfermedad_catastrofica"] == 0
    assert datos["necesidad_educativa_especial"] == 0


@pytest.mark.django_db
def test_una_alerta_desactivada_no_cuenta(escenario):
    from apps.expediente.services import desactivar_alerta

    alerta = AlertaClinica.objects.get(expediente=escenario["exp1"])
    desactivar_alerta(alerta)
    datos = services.informe_demografico(escenario["est"]["medicina"])
    assert datos["embarazo"] == 0


@pytest.mark.django_db
def test_filtra_por_fecha(escenario):
    Atencion.objects.filter(expediente=escenario["exp2"]).update(
        fecha_hora=timezone.now() - timedelta(days=30)
    )
    datos = services.informe_demografico(
        escenario["est"]["medicina"], desde=timezone.localdate() - timedelta(days=1)
    )
    assert datos["total_atenciones"] == 2  # solo las de exp1, recientes


@pytest.mark.django_db
def test_no_cuenta_atenciones_de_otro_servicio(escenario):
    datos = services.informe_demografico(escenario["est"]["psicologia"])
    assert datos["total_atenciones"] == 0


# ------------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_la_pantalla_muestra_los_totales(escenario):
    contenido = (
        _cliente(escenario["medico"]).get(reverse("reportes:informe_servicio")).content.decode()
    )
    assert "3 atención(es)" in contenido


@pytest.mark.django_db
def test_un_profesional_sin_servicio_no_entra(escenario):
    suelto = Usuario.objects.create_user(
        username="suelto_informe", password=CLAVE, rol_principal=Rol.PROFESIONAL
    )
    respuesta = _cliente(suelto).get(reverse("reportes:informe_servicio"))
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_no_se_puede_pedir_el_informe_de_un_servicio_ajeno(escenario):
    """El médico no puede pedir el informe de Psicología, que no es suyo."""
    psico = escenario["est"]["psicologia"]
    respuesta = _cliente(escenario["medico"]).get(
        reverse("reportes:informe_servicio"), {"servicio": psico.pk}
    )
    assert respuesta.status_code == 403


@pytest.mark.django_db
def test_el_pdf_se_genera(escenario):
    respuesta = _cliente(escenario["medico"]).get(reverse("reportes:informe_servicio_pdf"))
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_el_informe_no_esta_gateado_a_direccion(escenario):
    """
    A diferencia del tablero, este informe no exige rol de Dirección: basta
    con pertenecer al servicio. Es la diferencia central con `_solo_directivos`.
    """
    assert (
        _cliente(escenario["medico"]).get(reverse("reportes:informe_servicio")).status_code == 200
    )
