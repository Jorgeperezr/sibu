"""
La base institucional cargada: plantilla, diccionario, padrón y autocompletado.

Antes de esto el archivo se cargaba a ciegas —no había forma de saber qué
encabezados esperaba el sistema— y una vez cargado no había pantalla que
mostrara qué había entrado. Lo que estas pruebas fijan es sobre todo eso: que
la plantilla y el diccionario salgan del mapeo y no de una lista escrita
aparte, que el padrón sea solo para quien administra, y que el autocompletado
no se convierta en un volcado del padrón para cualquier cuenta con sesión.
"""

import csv
import io

import pytest
from django.test import Client
from django.urls import reverse

from apps.academico import mapping, selectors
from apps.academico.models import DatoAcademico
from apps.academico.validators import validar_cedula_ecuatoriana
from apps.core.models import PeriodoAcademico
from apps.expediente.models import Persona
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


def _cuenta(username, rol):
    usuario = Usuario.objects.create_user(username=username, password=CLAVE, rol_principal=rol)
    cliente = Client()
    assert cliente.login(username=username, password=CLAVE)
    return usuario, cliente


@pytest.fixture
def periodo(db):
    return PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril–Agosto 2026",
        fecha_inicio="2026-04-01",
        fecha_fin="2026-08-31",
        vigente=True,
    )


@pytest.fixture
def cargado(periodo):
    """Dos personas con su fila académica, como las dejaría una carga aplicada."""
    datos = [
        ("1104567894", "María José", "Pérez Ríos", "Medicina", "Facultad de la Salud Humana"),
        ("1101002002", "Luis Alberto", "Torres Ochoa", "Computación", "Facultad de Energía"),
    ]
    for cedula, nombres, apellidos, carrera, facultad in datos:
        persona = Persona.objects.create(
            cedula=cedula,
            nombres=nombres,
            apellidos=apellidos,
            tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
            sexo="Mujer",
        )
        DatoAcademico.objects.create(
            persona=persona,
            periodo=periodo,
            carrera=carrera,
            facultad=facultad,
            ciclo="3",
            estado="Matriculado",
        )
    return periodo


# ------------------------------------------------------- plantilla y diccionario


@pytest.mark.django_db
def test_la_plantilla_trae_todas_las_columnas_canonicas_sin_repetir():
    """
    La plantilla se genera del mapeo. Si mañana se añade una columna allí y
    aquí no aparece, es que alguien creó una segunda lista en paralelo.
    """
    filas = list(csv.reader(io.StringIO(selectors.plantilla_csv())))
    encabezados = filas[0]
    assert len(encabezados) == len(set(encabezados)), "hay encabezados repetidos"
    assert set(encabezados) == mapping.columnas_canonicas()


@pytest.mark.django_db
def test_la_plantilla_trae_una_fila_de_ejemplo_con_cedula_valida():
    """
    Una cédula de ejemplo que no pasara el módulo 10 haría que la primera
    prueba de carga de quien use la plantilla fallara sin motivo.
    """
    filas = list(csv.DictReader(io.StringIO(selectors.plantilla_csv())))
    assert len(filas) == 1
    for obligatoria in mapping.COLUMNAS_OBLIGATORIAS:
        assert filas[0][obligatoria], f"la fila de ejemplo no llena {obligatoria}"
    assert validar_cedula_ecuatoriana(filas[0]["cedula"])


@pytest.mark.django_db
def test_el_diccionario_lista_cada_columna_exactamente_una_vez():
    listadas = [c["nombre"] for g in selectors.diccionario() for c in g["columnas"]]
    assert len(listadas) == len(set(listadas))
    assert set(listadas) == mapping.columnas_canonicas()
    assert selectors.total_columnas() == len(listadas)


@pytest.mark.django_db
def test_el_diccionario_marca_las_obligatorias_y_las_que_alertan():
    por_nombre = {c["nombre"]: c for g in selectors.diccionario() for c in g["columnas"]}
    assert por_nombre["cedula"]["obligatoria"] is True
    assert por_nombre["celular"]["obligatoria"] is False
    assert por_nombre["estudiante_gestacion"]["alerta"] is True
    assert por_nombre["celular"]["alerta"] is False


@pytest.mark.django_db
def test_la_plantilla_se_descarga_como_csv(db):
    assert Client().get(reverse("academico:plantilla")).status_code == 302  # sin sesión, al login

    _, cliente = _cuenta("admin_plantilla", Rol.ADMIN_GENERAL)
    respuesta = cliente.get(reverse("academico:plantilla"))
    assert respuesta.status_code == 200
    assert "text/csv" in respuesta["Content-Type"]
    assert "plantilla-base-institucional.csv" in respuesta["Content-Disposition"]
    # BOM: sin él Excel abre el archivo en Latin-1 y parte las tildes.
    assert respuesta.content.startswith(b"\xef\xbb\xbf")


@pytest.mark.django_db
def test_solo_quien_administra_descarga_la_plantilla_y_ve_el_diccionario(db):
    est = crear_estructura()
    profesional, _ = crear_profesional("medico_padron", est["medicina"], est["salud"])
    profesional.set_password(CLAVE)
    profesional.save()
    cliente = Client()
    assert cliente.login(username="medico_padron", password=CLAVE)
    for nombre in ("academico:plantilla", "academico:diccionario", "academico:padron"):
        assert cliente.get(reverse(nombre)).status_code == 302, nombre


# ------------------------------------------------------------------- el padrón


@pytest.mark.django_db
def test_el_padron_muestra_lo_cargado(cargado):
    _, cliente = _cuenta("admin_padron", Rol.ADMIN_GENERAL)
    contenido = cliente.get(reverse("academico:padron")).content.decode()
    assert "1104567894" in contenido
    assert "Pérez Ríos" in contenido
    assert "Computación" in contenido


@pytest.mark.django_db
def test_el_padron_busca_por_cedula_nombre_facultad_o_carrera(cargado):
    _, cliente = _cuenta("admin_busca", Rol.ADMIN_GENERAL)
    contenido = cliente.get(reverse("academico:padron"), {"q": "Torres"}).content.decode()
    assert "Torres Ochoa" in contenido
    assert "Pérez Ríos" not in contenido

    contenido = cliente.get(reverse("academico:padron"), {"q": "Medicina"}).content.decode()
    assert "Pérez Ríos" in contenido
    assert "Torres Ochoa" not in contenido


@pytest.mark.django_db
def test_el_padron_filtra_por_periodo(cargado):
    otro = PeriodoAcademico.objects.create(
        codigo="2025-2",
        nombre="Octubre–Febrero 2025",
        fecha_inicio="2025-10-01",
        fecha_fin="2026-02-28",
    )
    _, cliente = _cuenta("admin_periodo", Rol.ADMIN_GENERAL)
    contenido = cliente.get(reverse("academico:padron"), {"periodo": otro.pk}).content.decode()
    assert "1104567894" not in contenido


# ------------------------------------------------------------ autocompletado


@pytest.mark.django_db
def test_autocompleta_por_cedula_y_por_nombres(cargado):
    est = crear_estructura()
    usuario, _ = crear_profesional("medico_auto", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_auto", password=CLAVE)

    por_cedula = cliente.get(reverse("academico:autocompletar"), {"q": "110456"}).json()
    assert [r["cedula"] for r in por_cedula["resultados"]] == ["1104567894"]
    assert por_cedula["resultados"][0]["carrera"] == "Medicina"

    por_nombre = cliente.get(reverse("academico:autocompletar"), {"q": "Torres"}).json()
    assert [r["cedula"] for r in por_nombre["resultados"]] == ["1101002002"]


@pytest.mark.django_db
def test_el_autocompletado_calla_con_menos_de_tres_caracteres(cargado):
    est = crear_estructura()
    usuario, _ = crear_profesional("medico_corto", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_corto", password=CLAVE)
    assert cliente.get(reverse("academico:autocompletar"), {"q": "11"}).json()["resultados"] == []


@pytest.mark.django_db
def test_el_autocompletado_no_lo_abre_cualquier_cuenta_con_sesion(cargado):
    """
    Sin este permiso, el autocompletado sería un volcado del padrón —nombre,
    cédula, carrera, correo— accesible a un usuario del portal.
    """
    _, cliente = _cuenta("estudiante_curioso", Rol.USUARIO_FINAL)
    assert cliente.get(reverse("academico:autocompletar"), {"q": "Torres"}).status_code == 403


@pytest.mark.django_db
def test_el_autocompletado_no_dice_que_servicio_atiende_a_nadie(cargado):
    """
    El sello de Psicología: saber que a alguien lo atiende Psicología ya es
    contenido. El autocompletado devuelve matrícula, nada más.
    """
    est = crear_estructura()
    usuario, _ = crear_profesional("medico_sello", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_sello", password=CLAVE)
    resultados = cliente.get(reverse("academico:autocompletar"), {"q": "Torres"}).json()[
        "resultados"
    ]
    prohibidas = {"servicio", "servicios", "atenciones", "diagnostico", "expediente", "alertas"}
    assert not (prohibidas & set(resultados[0]))


@pytest.mark.django_db
def test_el_autocompletado_no_crea_expedientes(cargado):
    """
    A diferencia de la búsqueda por cédula, teclear en una caja no puede
    materializar un expediente: se dispara con cada pulsación.
    """
    from apps.expediente.models import Expediente

    est = crear_estructura()
    usuario, _ = crear_profesional("medico_no_crea", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="medico_no_crea", password=CLAVE)
    antes = Expediente.objects.count()
    cliente.get(reverse("academico:autocompletar"), {"q": "1104567894"})
    assert Expediente.objects.count() == antes
