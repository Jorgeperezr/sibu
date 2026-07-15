"""Pruebas de SignosVitales y su reutilización desde Medicina."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.enfermeria.models import SignosVitales
from apps.enfermeria.services import signos_del_dia, ultimo_triaje
from apps.expediente.tests.factories import (crear_estructura, crear_expediente,
                                              crear_profesional)


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    _, enfermera = crear_profesional("enfermera", est["medicina"], est["salud"])
    exp = crear_expediente(cedula="1104567890")
    return {"est": est, "enfermera": enfermera, "exp": exp}


@pytest.mark.django_db
def test_signos_calcula_imc_automaticamente(escenario):
    sv = SignosVitales.objects.create(
        expediente=escenario["exp"],
        peso=Decimal("70"), talla=Decimal("1.70"),
        responsable=escenario["enfermera"],
    )
    assert sv.imc == Decimal("24.2")


@pytest.mark.django_db
def test_signos_sin_peso_no_calcula_imc(escenario):
    sv = SignosVitales.objects.create(
        expediente=escenario["exp"],
        temperatura=Decimal("37.5"), fc=88,
        responsable=escenario["enfermera"],
    )
    assert sv.imc is None


@pytest.mark.django_db
def test_signos_del_dia_solo_los_de_hoy(escenario):
    with freeze_time("2026-01-05 14:00:00"):
        SignosVitales.objects.create(
            expediente=escenario["exp"], temperatura=Decimal("36.5"),
            responsable=escenario["enfermera"],
        )
    with freeze_time("2026-01-06 10:00:00"):
        SignosVitales.objects.create(
            expediente=escenario["exp"], temperatura=Decimal("37.0"),
            responsable=escenario["enfermera"],
        )
        SignosVitales.objects.create(
            expediente=escenario["exp"], temperatura=Decimal("37.2"),
            responsable=escenario["enfermera"],
        )
        hoy = signos_del_dia(escenario["exp"])
        assert hoy.count() == 2


@pytest.mark.django_db
def test_ultimo_triaje_reciente(escenario):
    """El último triaje dentro de las últimas 12h se recupera para Medicina."""
    with freeze_time("2026-01-06 09:00:00"):
        SignosVitales.objects.create(
            expediente=escenario["exp"], temperatura=Decimal("37.0"), fc=85,
            responsable=escenario["enfermera"],
        )
    with freeze_time("2026-01-06 10:30:00"):
        triaje = ultimo_triaje(escenario["exp"])
        assert triaje is not None
        assert triaje.temperatura == Decimal("37.0")


@pytest.mark.django_db
def test_ultimo_triaje_expirado_devuelve_none(escenario):
    """Un triaje de hace 20h ya no cuenta."""
    with freeze_time("2026-01-05 08:00:00"):
        SignosVitales.objects.create(
            expediente=escenario["exp"], temperatura=Decimal("36.5"),
            responsable=escenario["enfermera"],
        )
    with freeze_time("2026-01-06 10:00:00"):
        assert ultimo_triaje(escenario["exp"]) is None
