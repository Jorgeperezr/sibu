"""
Capa visual (sprint 14).

No se prueban colores —eso es diseño, no lógica—, sino que el nuevo base.html
no rompa nada: que las páginas rendericen, que el favicon inline evite el 404, y
que los alerts se sigan pintando. Es una red de seguridad para un cambio que
toca la plantilla de la que heredan las 36.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import Seccion, Servicio
from apps.expediente.tests.factories import crear_estructura
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def admin(db):
    crear_estructura()
    becas_sec, _ = Seccion.objects.get_or_create(codigo="becas", defaults={"nombre": "Becas"})
    Servicio.objects.get_or_create(
        codigo="becas-y-ayudas-economicas",
        defaults={"nombre": "Becas", "seccion": becas_sec},
    )
    return Usuario.objects.create_user(
        username="admin", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )


@pytest.mark.django_db
def test_la_portada_renderiza_con_el_nuevo_base(admin):
    c = Client()
    c.login(username="admin", password=CLAVE)
    r = c.get(reverse("inicio"))
    assert r.status_code == 200
    cuerpo = r.content.decode()
    assert "sibu-footer" in cuerpo
    assert "css/sibu.css" in cuerpo


@pytest.mark.django_db
def test_el_favicon_inline_evita_el_404(admin):
    """Antes /favicon.ico daba 404 en cada carga. Ahora hay un icono inline."""
    c = Client()
    c.login(username="admin", password=CLAVE)
    cuerpo = c.get(reverse("inicio")).content.decode()
    assert 'rel="icon"' in cuerpo
    assert "data:image/svg+xml" in cuerpo


@pytest.mark.django_db
def test_la_pagina_de_login_usa_los_estilos(db):
    c = Client()
    cuerpo = c.get(reverse("login")).content.decode()
    assert "css/sibu.css" in cuerpo
    assert "sibu-footer" in cuerpo


@pytest.mark.django_db
def test_el_login_incorrecto_muestra_su_error(db):
    """Un flujo real que produce un alert visible con el nuevo base."""
    Usuario.objects.create_user(username="alguien", password=CLAVE)
    c = Client()
    cuerpo = c.post(reverse("login"), {"username": "alguien", "password": "mal"}).content.decode()
    assert "alert" in cuerpo


@pytest.mark.django_db
def test_modulos_que_el_admin_ve_renderizan_sin_romperse(admin):
    """
    Humo sobre módulos que heredan de base.html: cambiar la plantilla base no
    debe tumbar ninguno. Se usan los que el admin ve por rol (reportes) y las
    rutas generales (búsqueda de expedientes), no las bandejas que exigen un
    servicio asignado —su 403 es RBAC correcto, no un fallo de plantilla—.
    """
    c = Client()
    c.login(username="admin", password=CLAVE)
    for nombre in ("reportes:tablero", "expediente:buscar", "inicio"):
        r = c.get(reverse(nombre))
        assert r.status_code == 200, f"{nombre} devolvió {r.status_code}"
        assert "sibu-footer" in r.content.decode()
