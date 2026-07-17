"""
Qué se puede mandar a firmar fuera de la institución.

Firmar con FirmaEC implica que el PDF **sale de SIBU**: viaja al servicio
`firmadigital-servicio` y se almacena temporalmente en su base de datos antes
de volver firmado (manual 11).

Eso choca de frente con la decisión del cliente sobre Psicología: su contenido
no es accesible para nadie fuera del servicio, ni para Dirección, ni con
break-the-glass. Un informe psicológico enviado a un firmador externo sale del
perímetro donde ese sello se puede sostener — y si el servicio FirmaEC es el
centralizado del MINTEL, sale además de la UNL.

El RBAC no puede detener esto: la fuga no ocurriría por un permiso mal puesto
sino por una tubería legítima. Por eso la puerta está aquí y cerrada por
defecto.
"""

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES


def verificar_puede_salir_a_firmar(atencion) -> None:
    """
    Lanza ValidationError si el contenido no puede salir hacia FirmaEC.

    Se permite solo si la institución declara explícitamente que su despliegue
    de FirmaEC es descentralizado y está dentro de su propia infraestructura
    (`FIRMAEC_DESCENTRALIZADO_PROPIO = True`). Es una afirmación de la
    institución sobre su topología, no algo que SIBU pueda verificar solo: por
    eso es una decisión consciente y auditable, no un valor por defecto.
    """
    codigo = atencion.servicio.codigo
    if codigo not in SERVICIOS_CONFIDENCIALES:
        return

    if not getattr(settings, "FIRMAEC_DESCENTRALIZADO_PROPIO", False):
        raise ValidationError(
            f"El contenido de {atencion.servicio.nombre} es confidencial y no puede "
            "enviarse a un firmador fuera de la institución. Para habilitarlo, la UNL "
            "debe desplegar FirmaEC descentralizado en su propia infraestructura y "
            "declararlo en FIRMAEC_DESCENTRALIZADO_PROPIO."
        )
