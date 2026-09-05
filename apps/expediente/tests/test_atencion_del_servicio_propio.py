"""
Una atención se abre en el servicio propio, no en el de otro.

Ninguno de los cuatro servicios que abren atención lo comprobaba: recibían un
`PerfilProfesional` cualquiera y lo grababan como tratante. En Medicina había
incluso un fragmento muerto que lo decía —«placeholder: la validación de
servicio-profesional es de RBAC»— y no hacía nada.

En Psicología eso era una escalada al servicio sellado (ver
`psicologia/tests/test_api_escalada.py`). En los otros tres no lo es, pero un
odontólogo abriendo una consulta médica a su nombre ensucia el expediente y la
firma: quien conste como tratante es quien responde por lo escrito.
"""

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import Seccion, Servicio
from apps.expediente.tests.factories import crear_expediente, crear_profesional


@pytest.fixture
def dos_servicios(db):
    salud, _ = Seccion.objects.get_or_create(codigo="salud", defaults={"nombre": "Salud"})
    psicoped, _ = Seccion.objects.get_or_create(
        codigo="psicopedagogica", defaults={"nombre": "Psicopedagógica"}
    )
    servicios = {}
    for codigo, nombre, seccion in (
        ("medicina", "Medicina", salud),
        ("odontologia", "Odontología", salud),
        ("psicopedagogia", "Psicopedagogía", psicoped),
    ):
        servicios[codigo], _ = Servicio.objects.get_or_create(
            codigo=codigo, defaults={"nombre": nombre, "seccion": seccion}
        )
    ajeno, perfil_ajeno = crear_profesional("intruso", servicios["odontologia"], salud)
    return {"servicios": servicios, "perfil_ajeno": perfil_ajeno, "salud": salud}


def _abridores():
    from apps.medicina import services as medicina
    from apps.odontologia import services as odontologia
    from apps.psicopedagogia import services as psicopedagogia

    return [
        ("medicina", medicina.crear_atencion_medicina),
        ("odontologia", odontologia.crear_atencion_odontologia),
        ("psicopedagogia", psicopedagogia.crear_ficha),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("codigo,abrir", _abridores(), ids=lambda v: getattr(v, "__name__", v))
def test_no_se_abre_una_atencion_en_un_servicio_ajeno(codigo, abrir, dos_servicios):
    from apps.expediente.models import Atencion

    perfil = dos_servicios["perfil_ajeno"]
    if codigo == "odontologia":  # el intruso SÍ es de odontología: se usa otro
        _, perfil = crear_profesional(
            "intruso2", dos_servicios["servicios"]["medicina"], dos_servicios["salud"]
        )
    with pytest.raises(ValidationError, match="No pertenece al servicio"):
        abrir(expediente=crear_expediente(), profesional=perfil, motivo="lo que sea")
    assert not Atencion.objects.filter(servicio__codigo=codigo).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("codigo,abrir", _abridores(), ids=lambda v: getattr(v, "__name__", v))
def test_el_profesional_del_servicio_sí_la_abre(codigo, abrir, dos_servicios):
    """La otra cara: cerrar de más dejaría a cada servicio sin poder atender."""
    _, perfil = crear_profesional(
        f"propio_{codigo}", dos_servicios["servicios"][codigo], dos_servicios["salud"]
    )
    resultado = abrir(expediente=crear_expediente(), profesional=perfil, motivo="Consulta")
    atencion = resultado if hasattr(resultado, "servicio") else resultado.atencion
    assert atencion.servicio.codigo == codigo
