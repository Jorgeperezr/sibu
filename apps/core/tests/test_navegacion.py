"""
La navegación derivada del RBAC.

La regla que importa: el menú no puede mostrar un enlace a algo que la vista
luego niega con 403, ni ocultar algo a lo que sí se tiene acceso. Se construye
desde `servicios_del_usuario`, la misma fuente que usan las vistas.
"""

import pytest
from django.test import Client

from apps.core.models import Servicio
from apps.core.navegacion import modulos_visibles
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def estructura(db):
    est = crear_estructura()
    # El seed real usa estos códigos; las pruebas los necesitan para el menú.
    from apps.core.models import Seccion

    salud = est["salud"]
    Servicio.objects.get_or_create(
        codigo="laboratorio-clinico", defaults={"nombre": "Laboratorio", "seccion": salud}
    )
    Servicio.objects.get_or_create(
        codigo="farmacia", defaults={"nombre": "Farmacia", "seccion": salud}
    )
    Servicio.objects.get_or_create(
        codigo="odontologia", defaults={"nombre": "Odontología", "seccion": salud}
    )
    psico_sec, _ = Seccion.objects.get_or_create(
        codigo="psicopedagogica", defaults={"nombre": "Psicopedagógica"}
    )
    Servicio.objects.get_or_create(
        codigo="psicopedagogia", defaults={"nombre": "Psicopedagogía", "seccion": psico_sec}
    )
    becas_sec, _ = Seccion.objects.get_or_create(codigo="becas", defaults={"nombre": "Becas"})
    Servicio.objects.get_or_create(
        codigo="becas-y-ayudas-economicas", defaults={"nombre": "Becas", "seccion": becas_sec}
    )
    return est


def _etiquetas(user):
    return {m.etiqueta for m in modulos_visibles(user)}


@pytest.mark.django_db
def test_un_profesional_de_laboratorio_ve_laboratorio_no_psicologia(estructura):
    """
    El caso central: el menú refleja el RBAC. Un profesional de Laboratorio no
    debe ver el enlace a Psicología, coherente con el 403 que recibiría.
    """
    lab = Servicio.objects.get(codigo="laboratorio-clinico")
    _, prof = crear_profesional("laboratorista", lab, lab.seccion)
    etiquetas = _etiquetas(prof.usuario)
    assert "Laboratorio" in etiquetas
    assert "Psicología" not in etiquetas


@pytest.mark.django_db
def test_un_psicologo_ve_psicologia(estructura):
    psico = Servicio.objects.get(codigo="psicologia")
    _, prof = crear_profesional("psicologo", psico, psico.seccion)
    assert "Psicología" in _etiquetas(prof.usuario)


@pytest.mark.django_db
def test_un_odontologo_ve_odontologia(estructura):
    odonto = Servicio.objects.get(codigo="odontologia")
    _, prof = crear_profesional("dentista_nav", odonto, odonto.seccion)
    assert "Odontología" in _etiquetas(prof.usuario)


@pytest.mark.django_db
def test_quien_no_es_de_odontologia_no_ve_odontologia(estructura):
    """Coherente con el 403 de la bandeja: mismo criterio en menú y vista."""
    lab = Servicio.objects.get(codigo="laboratorio-clinico")
    _, prof = crear_profesional("lab_sin_odonto", lab, lab.seccion)
    assert "Odontología" not in _etiquetas(prof.usuario)


@pytest.mark.django_db
def test_el_admin_ve_todos_los_modulos(estructura):
    """Admin navega todo; el acceso fino al contenido lo resuelve cada vista."""
    u = Usuario.objects.create_user(
        username="admin", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )
    etiquetas = _etiquetas(u)
    assert {"Odontología", "Laboratorio", "Farmacia", "Psicología", "Becas"} <= etiquetas


@pytest.mark.django_db
def test_solo_direccion_ve_reportes(estructura):
    lab = Servicio.objects.get(codigo="laboratorio-clinico")
    _, prof = crear_profesional("lab2", lab, lab.seccion)
    assert "Reportes" not in _etiquetas(prof.usuario)

    director = Usuario.objects.create_user(
        username="dir", password=CLAVE, rol_principal=Rol.DIRECTOR
    )
    assert "Reportes" in _etiquetas(director)


@pytest.mark.django_db
def test_los_modulos_generales_los_ve_cualquier_profesional(estructura):
    """Agenda, derivaciones y talleres no dependen de un servicio."""
    lab = Servicio.objects.get(codigo="laboratorio-clinico")
    _, prof = crear_profesional("lab3", lab, lab.seccion)
    etiquetas = _etiquetas(prof.usuario)
    assert {"Mi agenda", "Derivaciones", "Talleres", "Expedientes"} <= etiquetas


@pytest.mark.django_db
def test_el_usuario_del_portal_solo_ve_su_portal(estructura):
    """Un estudiante no navega módulos internos: su sitio es /portal/."""
    u = Usuario.objects.create_user(
        username="estu", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    etiquetas = _etiquetas(u)
    assert etiquetas == {"Mi portal"}


@pytest.mark.django_db
def test_un_usuario_sin_perfil_no_ve_modulos_de_servicio(estructura):
    """Sin perfil no hay servicios: solo los módulos generales, no los clínicos."""
    u = Usuario.objects.create_user(username="pelado", password=CLAVE, rol_principal=Rol.CONSULTA)
    etiquetas = _etiquetas(u)
    assert "Laboratorio" not in etiquetas
    assert "Psicología" not in etiquetas


@pytest.mark.django_db
def test_anonimo_no_ve_nada(estructura):
    from django.contrib.auth.models import AnonymousUser

    assert modulos_visibles(AnonymousUser()) == []


# --------------------------------------------------------------------------
# Integración: la cabecera y el redirect
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_la_cabecera_muestra_los_modulos_del_usuario(estructura):
    psico = Servicio.objects.get(codigo="psicologia")
    u, _ = crear_profesional("psi2", psico, psico.seccion)
    u.set_password(CLAVE)
    u.save()
    c = Client()
    c.login(username="psi2", password=CLAVE)
    cuerpo = c.get("/").content.decode()
    assert "Psicología" in cuerpo
    assert "Cerrar sesión" or "Salir" in cuerpo


@pytest.mark.django_db
def test_expediente_raiz_redirige_a_buscar(estructura):
    """La ruta obvia ya no muere en 404: lleva a la búsqueda."""
    Usuario.objects.create_user(username="admin2", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL)
    c = Client()
    c.login(username="admin2", password=CLAVE)
    r = c.get("/expediente/")
    assert r.status_code == 302
    assert r.url.endswith("/expediente/buscar/")
