# SIBU — Sistema Integral de Bienestar Universitario (UNL)

Django 5.1 + DRF + PostgreSQL 16 + Bootstrap 5. Nueve servicios: Medicina,
Enfermería, Odontología, Laboratorio, Farmacia, Psicología, Psicopedagogía,
Trabajo Social y Becas. Más citas, expediente único, derivaciones, firma,
talleres, portal del estudiante y tablero de gestión.

## Reglas del dominio que no se negocian

- **El sello de Psicología es absoluto.** El contenido clínico de Psicología no
  es accesible fuera del servicio: ni Dirección, ni administración, ni
  break-glass. Sin excepciones. Antes de tocar RBAC, derivaciones, firma,
  portal o reportes, comprobar que no se abre una rendija.
- **Los tableros muestran gestión, no contenido.** En servicios confidenciales,
  un conteo de pacientes distintos < 5 se reporta como `<5` (K_MINIMO): un
  conteo pequeño identifica.
- **Un taller no es una atención clínica.** Registrar a alguien en un taller no
  le abre expediente.
- **Verificar matrícula no suspende una beca.** El sistema informa; la decisión
  es de Trabajo Social. Suspender exige causal escrita.
- **El portal aísla por identidad, no por rol.** Toda consulta parte del
  expediente vinculado; ningún recurso se busca por id de URL sin filtrar.
- **Ausencia de dato no es prueba de ausencia.** Sin datos académicos cargados
  no se concluye "no matriculado".
- **El estamento es `Persona.tipo_vinculo`, no un campo nuevo.** Cuatro
  estamentos (estudiante, docente, administrativo, trabajador) más «externo»,
  que no lo es. Cada estamento tiene su propia base con columnas distintas y se
  declara al cargar; sin declararlo no se escribe.
- **Un anexo nombra a personas.** La nómina y las evidencias del informe
  estadístico llevan la identidad protegida por omisión (sin cédula, teléfono,
  correo ni número de expediente —que es `EXP-<cédula>`—) y no existen para los
  servicios confidenciales.

## Trampas técnicas que ya nos costaron caro

- **Insertar una función encima de otra decorada le roba el decorador.** Meter
  un `def` nuevo entre `@transaction.atomic` y la función que decoraba deja a
  la original sin transacción y a la nueva envuelta en una. No lo ve ninguna
  prueba de comportamiento normal: lo ve una que compruebe que un fallo a mitad
  no deja el dato partido.
- **Auditar y abortar no caben en la misma transacción.** Registrar un rechazo
  dentro de `@transaction.atomic` y luego lanzar ValidationError revierte el
  propio log. Pasó dos veces (firma, portal).
- **Ejecutar `ruff check .` y `ruff format --check .` por separado, sin `&&`.**
  El `&&` oculta el fallo de formato y tumba el CI.
- **Las pruebas de configuración deben FIJAR lo que afirman, no heredarlo del
  entorno.** Una prueba que lee `DATABASES` o `BASE_DIR` del entorno pasa en una
  máquina y falla en otra.
- **Cédulas de prueba deben pasar el módulo 10 ecuatoriano**: `1100000007`,
  `1700000001` son válidas; `1104567890` NO.
- **Zona horaria America/Guayaquil**: usar `timezone.localtime()`, no comparar
  UTC contra `localdate()`.
- **Un decimal con coma es un decimal: `apps/core/numeros.py` es la única
  lectura.** Aquí se escribe 450,50. El sistema lo leía de cuatro maneras
  —×100 al cargar, cero al sumar, vacío en signos vitales, bien solo en
  Laboratorio—, todas silenciosas y todas alimentando el estrato que orienta
  una beca. No escribir otra conversión: `a_decimal` (lanza), `a_decimal_o`
  (indulgente, para lo YA guardado), `a_entero`, `es_ambiguo`. Y `Decimal("8,5")`
  lanza `InvalidOperation`, que NO es `ValidationError`: un `except
  (ValidationError, KeyError)` no lo atrapa.
- **Guardar lo leído, no lo tecleado.** Validar «8,5» y luego guardar la cadena
  en un campo decimal vuelve a romper al escribir, donde ya no hay a quién
  avisar.
- **Indulgente con lo guardado, estricto con lo tecleado.** Un cálculo sobre
  fichas viejas no puede reventar por un «no aplica»; un formulario que acaba
  de recibir «450,5O» tiene que devolverlo, porque si lo ignora ese ingreso
  desaparece del hogar.
- **Un cero es falsy: `{% if valor %}` lo esconde.** Escondía el puntaje 0,00
  SBU —que es «extrema vulnerabilidad»— y el rango de laboratorio que empieza
  en 0. Usar `{% if valor is not None %}`; distinguir el cero de la ausencia es
  el objetivo, no borrar la ausencia.
- **Un color semántico de Bootstrap no vale para un mapa clínico.** La línea
  gráfica tiñe `primary` con el verde de la UNL, así que el diente obturado
  (`btn-primary`) salió del mismo verde que el sano (`btn-success`): 1,14:1 de
  contraste. Paleta propia, y el color nunca decide solo —cada pieza lleva su
  inicial, porque el 8 % de los hombres no distingue rojo de verde—.
- **Un atributo que no existe no da error en una plantilla: da un hueco.**
  `{{ receta.codigo }}` sobre un modelo cuyo campo es `numero` responde 200 y
  pinta vacío. Ninguna prueba de estado ni de contexto lo ve; lo ve una que
  compruebe que lo propio APARECE (`assert receta.numero in contenido`).
- **Comentarios de plantilla `{# #}` solo funcionan en una línea.** Para varias,
  `{% comment %}`.
- **`pluralize` no sirve para una palabra con tilde en la última sílaba.**
  «atención» → `atencion{{ n|pluralize:"es" }}` imprime «1 atencion», sin
  tilde. Usar `{{ n|plural:"atención,atenciones" }}` (`apps/core/templatetags/
  textos.py`); una prueba barre las plantillas buscando la recaída.
- **El mismo valor llega escrito de varias maneras.** Cuatro bases
  institucionales, cuatro escrituras: «F», «f», «Femenino», «Mujer». El informe
  daba cuatro filas para dos grupos. Se agrupa al CONTAR en
  `core.vocabulario.normalizar`, nunca al guardar, y solo hay sinónimos donde
  el vocabulario es oficial y cerrado: género e identidad son libres a
  propósito y ahí solo se unifica la capitalización.
- **Un formulario no envía las casillas desmarcadas.** «Quité todas las
  variables» y «acabo de abrir la pantalla» llegan idénticos al servidor: hace
  falta un testigo oculto (`elegir=1`) para distinguirlos, o el informe sale con
  todo justo cuando se pidió que no.
- **Una cifra y su evidencia no pueden calcularse dos veces.** El informe y sus
  anexos comparten `reportes.services.etiquetar`; dos consultas parecidas se
  separan y el anexo acaba desmintiendo lo que respalda.
- `auto_now_add` sobre tabla existente falla sin default.

## Convenciones

- Todo en español: código, comentarios, commits (Conventional Commits), UI.
- Estructura por app: `models`, `services` (lógica), `selectors` (consultas),
  `api`, `serializers`, `views`, `urls`, `tests`.
- Las integraciones externas van tras un **provider** intercambiable
  (`AcademicoProvider`, `FirmadorProvider`, `AlmacenEvidenciasProvider`): el
  sistema debe funcionar sin ellas. Firma y Google Drive vienen deshabilitados
  por defecto.
- La navegación se deriva del RBAC (`apps/core/navegacion.py`), nunca de listas
  fijas paralelas.
- Prosa concisa, sin redundancia. Citas APA 7 en docs cuando aplique.

## Comandos

    make up        # levanta la web (deriva variables de Codespaces)
    make perfil    # perfil de dev con todos los servicios (solo DEBUG=True)
    make setup     # migraciones + datos base + RBAC
    make test      # pytest con cobertura
    make lint      # ruff check, ruff format --check y bandit (separados)

Entorno docker-compose: PostgreSQL en el contenedor `db`, Redis en `redis`. No
existen `service postgresql` ni `redis-server` dentro del contenedor `web`.

## Antes de dar por terminado un cambio

    ruff check .
    ruff format --check .
    pytest apps -q          # deben pasar TODAS (315 al día de hoy)
    python manage.py check
    python manage.py makemigrations --check --dry-run
