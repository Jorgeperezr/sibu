"""
El profesional puede ver lo declarado y anotar lo que comprobó.

`AjusteDeServicio` existía entero —modelo, servicio, selectores y hasta el uso
en el informe estadístico— y **ninguna pantalla lo exponía**: era el motor sin
el volante. En consulta se identifica un embarazo que la ficha de matrícula no
declara y el profesional no tenía dónde ponerlo, así que o no se registraba o
alguien acababa editando la base institucional, que es la fuente para todo el
sistema.

Lo que se prueba es la regla, no el formulario: lo anotado vale para el
servicio que lo comprobó, la matrícula queda intacta y se puede volver atrás.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.expediente.models import AjusteDeServicio
from apps.expediente.selectors import valores_efectivos
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, _perfil = crear_profesional("medico_ajuste", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()
    cliente = Client()
    assert cliente.login(username="medico_ajuste", password=CLAVE)
    return {
        "est": est,
        "medico": medico,
        "cliente": cliente,
        "expediente": crear_expediente(cedula="1104567894"),
    }


@pytest.mark.django_db
def test_la_pantalla_ofrece_anotar_lo_comprobado(escenario):
    """Antes no había por dónde: el motor estaba y el volante no."""
    contenido = (
        escenario["cliente"]
        .get(reverse("expediente:detalle", args=[escenario["expediente"].pk]))
        .content.decode()
    )
    assert "comprobó" in contenido
    assert "Embarazo" in contenido
    assert reverse("expediente:ajustar", args=[escenario["expediente"].pk]) in contenido


@pytest.mark.django_db
def test_anotar_un_embarazo_no_toca_la_base_institucional(escenario):
    """
    El caso que lo motiva. La matrícula sigue diciendo lo que decía: es la
    fuente para el resto del sistema y nadie autorizó a reescribirla desde una
    consulta.
    """
    expediente = escenario["expediente"]
    escenario["cliente"].post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "gestacion", "valor": "Sí", "nota": "Confirmada en consulta, 12 semanas"},
        follow=True,
    )

    ajuste = AjusteDeServicio.objects.get(expediente=expediente, variable="gestacion")
    assert ajuste.valor == "Sí"
    assert ajuste.servicio == escenario["est"]["medicina"]

    filas = {f["variable"]: f for f in valores_efectivos(expediente, escenario["est"]["medicina"])}
    assert filas["gestacion"]["valor"] == "Sí"
    assert filas["gestacion"]["institucional"] != "Sí", "la matrícula no debe haber cambiado"


@pytest.mark.django_db
def test_lo_anotado_vale_solo_para_el_servicio_que_lo_comprobo(escenario):
    """Cada servicio reporta lo que él comprobó; lo que no, lo toma de la institución."""
    expediente = escenario["expediente"]
    escenario["cliente"].post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "gestacion", "valor": "Sí"},
        follow=True,
    )
    otro = {f["variable"]: f for f in valores_efectivos(expediente, escenario["est"]["psicologia"])}
    assert otro["gestacion"]["valor"] != "Sí"
    assert otro["gestacion"]["ajustado"] is False


@pytest.mark.django_db
def test_se_puede_volver_a_lo_declarado(escenario):
    """Que se pueda deshacer es lo que hace seguro anotar."""
    expediente = escenario["expediente"]
    url = reverse("expediente:ajustar", args=[expediente.pk])
    escenario["cliente"].post(url, {"variable": "gestacion", "valor": "Sí"}, follow=True)
    escenario["cliente"].post(url, {"variable": "gestacion", "accion": "quitar"}, follow=True)
    assert not AjusteDeServicio.objects.filter(expediente=expediente, variable="gestacion").exists()


@pytest.mark.django_db
def test_no_se_puede_ajustar_el_genero_ni_la_identidad(escenario):
    """
    Son declaraciones de la persona sobre sí misma. Que un servicio las
    «corrigiera» sería asignarle una identidad.
    """
    expediente = escenario["expediente"]
    respuesta = escenario["cliente"].post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "genero", "valor": "otro"},
        follow=True,
    )
    assert not AjusteDeServicio.objects.filter(variable="genero").exists()
    assert "declara" in respuesta.content.decode()


@pytest.mark.django_db
def test_un_formulario_incompleto_avisa_y_no_revienta(escenario):
    """Un `request.POST["variable"]` que no llega es un aviso, no un 500."""
    respuesta = escenario["cliente"].post(
        reverse("expediente:ajustar", args=[escenario["expediente"].pk]), {}, follow=True
    )
    assert respuesta.status_code == 200


@pytest.mark.django_db
def test_quien_no_ve_expedientes_no_ajusta(db):
    """El ajuste escribe sobre el expediente: exige el mismo permiso que abrirlo."""
    from apps.usuarios.models import Rol, Usuario

    expediente = crear_expediente(cedula="1712345675")
    Usuario.objects.create_user(username="ajeno", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    cliente = Client()
    assert cliente.login(username="ajeno", password=CLAVE)
    respuesta = cliente.post(
        reverse("expediente:ajustar", args=[expediente.pk]),
        {"variable": "gestacion", "valor": "Sí"},
    )
    assert respuesta.status_code == 403
    assert not AjusteDeServicio.objects.exists()
