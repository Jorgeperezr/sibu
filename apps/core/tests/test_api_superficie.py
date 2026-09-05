"""
Barrido de toda la superficie de la API, no de un endpoint a la vez.

Los agujeros de control de acceso aparecieron de uno en uno —nueve vistas web,
después la trazabilidad de derivaciones, después la lista de citas— y siempre
por el mismo camino: alguien registra un ViewSet nuevo con `IsAuthenticated` y
sin filtrar el queryset, y nadie vuelve a mirarlo.

Esta prueba recorre el router, así que un ViewSet registrado mañana entra solo.
Fija el mínimo que no se negocia: quien solo tiene una sesión —rol
USUARIO_FINAL, la cuenta de un estudiante— no lee datos de pacientes por
ninguna de las puertas registradas. Su propia información la ve por el portal,
que aísla por identidad.

**Siembra el sistema entero antes de mirar.** Sin datos, todas las listas
salen vacías y la prueba pasaría afirmando nada: sería peor que no tenerla,
porque daría por revisada una superficie que nadie revisó.

No comprueba que cada endpoint aplique su regla fina; comprueba que ninguno se
haya quedado sin ninguna.
"""

import pytest
from django.core.management import call_command
from django.test import Client

from api.v1.urls import router
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"

# Catálogos: no contienen datos de personas. Que un estudiante los lea no dice
# nada de nadie, y el portal necesita alguno. Se listan uno a uno, con su
# razón, para que añadir una excepción cueste pensarlo.
CATALOGOS = {
    "farmacia/medicamentos": "vademécum de la Unidad, sin pacientes",
    "laboratorio/examenes": "catálogo de exámenes, sin resultados",
    "odontologia/catalogo": "catálogo de procedimientos",
    "psicologia/escalas": "catálogo de escalas psicométricas, sin aplicaciones",
    "becas/tipos": "tipos de beca ofertados",
    "talleres": "oferta de talleres: es pública, y un taller no abre expediente",
}


@pytest.fixture
def sistema_sembrado(db, settings):
    """
    El sistema con actividad real en cada módulo: pacientes, atenciones,
    citas, recetas, órdenes de laboratorio, fichas, derivaciones y becas.
    """
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def _rutas():
    return [(prefijo, viewset.__name__) for prefijo, viewset, _b in router.registry]


def test_el_barrido_recorre_algo():
    """Si el router se reorganiza y esto queda vacío, la prueba pasaría sola."""
    assert len(_rutas()) >= 20


@pytest.mark.django_db
def test_hay_datos_que_filtrar(sistema_sembrado):
    """
    La prueba de abajo afirma «vacío». Esto comprueba que el vacío significa
    algo: que con una cuenta que sí puede ver, esos mismos endpoints traen
    filas. Sin esto, un fallo de siembra convertiría el barrido en un adorno.
    """
    from apps.core.management.commands.datos_demo import ADMIN

    cliente = Client()
    assert cliente.login(username=ADMIN["username"], password=ADMIN["clave"])

    con_filas = []
    for prefijo, _ in _rutas():
        respuesta = cliente.get(f"/api/v1/{prefijo}/")
        if respuesta.status_code != 200:
            continue
        datos = respuesta.json()
        filas = datos["results"] if isinstance(datos, dict) and "results" in datos else datos
        if filas:
            con_filas.append(prefijo)
    assert len(con_filas) >= 5, f"la siembra dejó casi todo vacío: {con_filas}"


@pytest.mark.django_db
def test_un_estudiante_no_lee_datos_de_pacientes_por_ninguna_puerta(sistema_sembrado):
    """
    O responde 403, o devuelve una lista vacía. Lo que no puede es devolver
    filas: cada una llevaría el nombre o la cédula de una persona atendida.
    """
    Usuario.objects.create_user(
        username="sonda_api", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    cliente = Client()
    assert cliente.login(username="sonda_api", password=CLAVE)

    filtraron = {}
    for prefijo, nombre_viewset in _rutas():
        if prefijo in CATALOGOS:
            continue
        respuesta = cliente.get(f"/api/v1/{prefijo}/")
        if respuesta.status_code != 200:
            continue
        datos = respuesta.json()
        filas = datos["results"] if isinstance(datos, dict) and "results" in datos else datos
        if filas:
            filtraron[f"/api/v1/{prefijo}/ ({nombre_viewset})"] = len(filas)

    assert filtraron == {}, f"le devolvieron filas a un estudiante: {filtraron}"
