"""
Tablero de gestión.

Las pruebas que importan: quién entra, y que los agregados de Psicología no
señalen a nadie.
"""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.core.models import Servicio
from apps.expediente.models import Atencion
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.reportes import services
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    psico = Servicio.objects.get(codigo="psicologia")
    _, medico = crear_profesional("medico", est["medicina"], est["salud"])
    _, psicologo = crear_profesional("psicologo", psico, psico.seccion)
    return {"est": est, "psico": psico, "medico": medico, "psicologo": psicologo}


def _atenciones(escenario, servicio, profesional, cedulas):
    for c in cedulas:
        exp = crear_expediente(cedula=c)
        Atencion.objects.create(
            expediente=exp,
            servicio=servicio,
            profesional=profesional,
            fecha_hora=timezone.now(),
        )


def _directivo(rol):
    u = Usuario.objects.create_user(username=f"dir{rol}", password=CLAVE, rol_principal=rol)
    return u


# --------------------------------------------------------------------------
# Supresión: los agregados no señalan a nadie
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_conteo_pequeno_de_psicologia_se_suprime(escenario):
    """
    Un conteo de 2 pacientes en Psicología identifica casi tanto como un
    nombre. Bajo el umbral, se reporta '<5'.
    """
    _atenciones(escenario, escenario["psico"], escenario["psicologo"], ["1100000007", "1700000001"])
    filas = services.atenciones_por_servicio()
    fila = next(f for f in filas if f["servicio"] == escenario["psico"].nombre)
    assert fila["pacientes"] == services.SUPRIMIDO
    # El total de atenciones sí se muestra: es demanda del servicio, no identidad.
    assert fila["total"] == 2


@pytest.mark.django_db
def test_conteo_pequeno_de_medicina_no_se_suprime(escenario):
    """La supresión es para servicios confidenciales, no un velo general."""
    _atenciones(
        escenario, escenario["est"]["medicina"], escenario["medico"], ["1100000007", "1700000001"]
    )
    filas = services.atenciones_por_servicio()
    fila = next(f for f in filas if f["servicio"] == escenario["est"]["medicina"].nombre)
    assert fila["pacientes"] == 2


@pytest.mark.django_db
def test_el_tablero_no_contiene_nombres_ni_cedulas(escenario):
    """Cero identidades: se recorre el tablero serializado completo."""
    import json

    exp_cedula = "1100000007"
    _atenciones(escenario, escenario["psico"], escenario["psicologo"], [exp_cedula])
    datos = services.tablero_general()
    volcado = json.dumps(datos, default=str)
    assert exp_cedula not in volcado
    assert "Paciente" not in volcado  # nombre de las personas de factory


# --------------------------------------------------------------------------
# Acceso
# --------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("rol", [Rol.ADMIN_GENERAL, Rol.DIRECTOR, Rol.COORDINADOR])
def test_roles_directivos_entran(escenario, rol):
    _directivo(rol)
    c = Client()
    c.login(username=f"dir{rol}", password=CLAVE)
    assert c.get("/reportes/").status_code == 200


@pytest.mark.django_db
def test_un_profesional_no_entra_al_tablero(escenario):
    u, _ = crear_profesional("med9", escenario["est"]["medicina"], escenario["est"]["salud"])
    u.set_password(CLAVE)
    u.save()
    c = Client()
    c.login(username="med9", password=CLAVE)
    assert c.get("/reportes/").status_code == 403


@pytest.mark.django_db
def test_un_usuario_del_portal_no_entra_al_tablero(escenario):
    Usuario.objects.create_user(username="estu", password=CLAVE, rol_principal=Rol.USUARIO_FINAL)
    c = Client()
    c.login(username="estu", password=CLAVE)
    assert c.get("/reportes/").status_code == 403


@pytest.mark.django_db
def test_la_exportacion_queda_auditada(escenario):
    from apps.auditoria.models import LogAuditoria

    _directivo(Rol.DIRECTOR)
    c = Client()
    c.login(username=f"dir{Rol.DIRECTOR}", password=CLAVE)
    r = c.get("/reportes/exportar/")
    assert r.status_code == 200
    assert r["Content-Type"] == "text/csv"
    assert LogAuditoria.objects.filter(
        modulo="reportes", accion=LogAuditoria.Accion.EXPORT
    ).exists()


# --------------------------------------------------------------------------
# Indicadores
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_ausentismo_sobre_citas_finalizadas_no_sobre_el_total(escenario):
    """Contra el total (con futuras y canceladas) el indicador mentiría."""
    from apps.citas.models import Cita

    exp = crear_expediente(cedula="1100000007")
    base = timezone.now() - timedelta(days=3)
    for i, estado in enumerate(
        [
            Cita.Estado.ATENDIDA,
            Cita.Estado.ATENDIDA,
            Cita.Estado.NO_ASISTIO,
            Cita.Estado.RESERVADA,
            Cita.Estado.CANCELADA,
        ]
    ):
        Cita.objects.create(
            expediente=exp,
            servicio=escenario["est"]["medicina"],
            profesional=escenario["medico"],
            fecha_hora=base + timedelta(hours=i),
            estado=estado,
        )
    ind = services.citas_indicadores()
    # 1 ausencia de 3 finalizadas = 33.3, no 1 de 5 = 20
    assert ind["ausentismo_pct"] == 33.3


@pytest.mark.django_db
def test_tablero_vacio_no_revienta(escenario):
    datos = services.tablero_general()
    assert datos["citas"]["ausentismo_pct"] is None
    assert datos["psicopedagogia"]["variacion_promedio"] is None
    assert datos["odontologia"]["promedio"] == 0
