"""
Barrido de las pantallas web, el gemelo del de la API.

El mismo descuido que dejó doce endpoints abiertos dejó pantallas abiertas:
`@login_required` a secas, que solo pregunta si hay sesión, nunca de quién.
El Sprint 7b corrigió nueve vistas así; este barrido recorre el resolver de
URLs para que la décima no haga falta encontrarla a mano.

Lo que encontró al escribirse:

- `/citas/reservar/` — un estudiante reservaba una cita para cualquier
  expediente con cualquier profesional, Psicología incluida.
- `/citas/_persona/` — la tercera puerta a `resolver_por_cedula`, después de
  la vista `buscar` y de la API: devuelve los datos de la persona y de paso le
  ABRE un expediente.
- `/citas/_profesionales/` — el directorio de quién atiende en cada servicio.

Lo que un estudiante SÍ puede abrir se lista con su razón: si mañana aparece
una pantalla nueva en esa lista, hay que justificarla a mano.
"""

import re

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import get_resolver

from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"

# Pantallas que un estudiante debe poder abrir, y por qué.
PERMITIDAS = {
    "inicio": "portada pública",
    "login": "iniciar sesión",
    "logout": "cerrar sesión",
    "password_change": "cambiar su propia contraseña",
    "password_change_done": "confirmación de lo anterior",
    "password_reset": "recuperar su propia contraseña",
    "password_reset_done": "confirmación de lo anterior",
    "password_reset_confirm": "recuperar su propia contraseña",
    "password_reset_complete": "confirmación de lo anterior",
    "mi_perfil": "su propia ficha",
    "vincular": "portal del estudiante: vincula SU expediente, por identidad",
}
# Prefijos que este barrido no cubre: la API tiene el suyo.
FUERA = ("api/", "admin/", "__debug__", "static", "media", "portal/")


def _rutas():
    encontradas = []

    def recorre(patrones, prefijo=""):
        for p in patrones:
            if hasattr(p, "url_patterns"):
                recorre(p.url_patterns, prefijo + str(p.pattern))
            else:
                encontradas.append((prefijo + str(p.pattern), p.name))

    recorre(get_resolver().url_patterns)
    return encontradas


@pytest.fixture
def sembrado(db, settings):
    settings.DEBUG = True
    call_command("preparar", verbosity=0)


def test_el_barrido_recorre_algo():
    assert len(_rutas()) >= 40


@pytest.mark.django_db
def test_un_estudiante_no_abre_ninguna_pantalla_de_gestion(sembrado):
    """
    Cada 200 inesperado es una pantalla que no pregunta quién entra. No se
    exige un código concreto —302 a login, 403, 404 son todos correctos—:
    se exige que no sea 200.
    """
    Usuario.objects.create_user(username="est_web", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    cliente = Client()
    assert cliente.login(username="est_web", password=CLAVE)

    abiertas = {}
    for patron, nombre in _rutas():
        if patron.startswith(FUERA) or "format" in patron or nombre in PERMITIDAS:
            continue
        url = "/" + re.sub(r"<[^>]+>", "1", patron)
        if "(" in url:
            continue
        try:
            respuesta = cliente.get(url)
        except Exception:
            # Una vista que revienta con un id inventado no es un agujero de
            # acceso; es otra cosa y no la juzga este barrido.
            continue
        if respuesta.status_code == 200:
            abiertas[url] = nombre

    assert abiertas == {}, f"pantallas abiertas a un estudiante: {abiertas}"
