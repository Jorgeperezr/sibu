"""
Plurales en español para las plantillas.

`pluralize` de Django pega una terminación al final de la palabra tal cual
está escrita, y en español eso falla cada vez que el singular lleva tilde en la
última sílaba: «atención» + «es» da «atencions» si se pega la s, y escribir
`atencion{{ n|pluralize:"es" }}` para esquivarlo imprime «1 atencion», sin
tilde. Ya estaba resuelto a mano en dos sitios —el subtítulo del Excel y la
pantalla de exportación, las dos con su comentario explicándolo— y se volvió a
colar en los anexos del informe: se veía «1 atencion» en pantalla y en el PDF.

Por eso el filtro pide las DOS formas, que es la única manera de no equivocarse:

    {{ n }} {{ n|plural:"atención,atenciones" }}
"""

from django import template

register = template.Library()


@register.filter
def plural(cantidad, formas: str) -> str:
    """
    La forma que toca según la cantidad. `formas` es "singular,plural".

    Uno es singular y todo lo demás plural, cero incluido: en español se dice
    «0 atenciones».
    """
    singular, _, plural_ = formas.partition(",")
    try:
        uno = int(cantidad) == 1
    except (TypeError, ValueError):
        uno = False
    return singular if uno else (plural_ or singular)
