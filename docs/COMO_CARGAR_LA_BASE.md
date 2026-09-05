# Cómo cargar la base de datos, paso a paso

Guía de uso. El detalle de las 157 columnas está en
`docs/CARGA_BASE_INSTITUCIONAL.md`; esto es el procedimiento.

## Antes de empezar

Entre con la cuenta de administración:

| | |
|---|---|
| Usuario | `1104346091` |
| Contraseña | `1104346091` |

Si el menú de la izquierda no muestra **Base institucional** bajo *Gestión*,
esa cuenta no tiene el permiso de carga. Compruébelo con `make cuentas` y
recréela con `make preparar`.

## Paso 1 — Descargar la plantilla

**Base institucional → Diccionario de columnas → Descargar plantilla CSV**

Baja un archivo con los encabezados exactos y una fila de ejemplo. Es la forma
de no equivocarse escribiéndolos a mano.

## Paso 2 — Llenar el archivo

Borre la fila de ejemplo y ponga una fila por persona.

Solo tres columnas son obligatorias: **`cedula`, `nombres`, `apellidos`**. El
resto puede ir vacío; cuantas más traiga, menos tendrá que digitar el
profesional después.

Tres cosas que rompen una carga, por orden de frecuencia:

1. **Guardar como «CSV UTF-8 (delimitado por comas)»**, no como «CSV» a secas.
   El «CSV» de Excel en Windows guarda en Latin-1 y parte las tildes de los
   encabezados; entonces `parroquia_procedencia` deja de reconocerse.
2. **Formatear la columna de la cédula como TEXTO antes de escribir.** Excel la
   trata como número: convierte `0912345678` en `912345678` y `1104567894` en
   `1,10457E+09`. El sistema repone el cero perdido; la notación científica ya
   no se puede recuperar.
3. **Fechas en `AAAA-MM-DD`.** También se aceptan `DD/MM/AAAA` y `DD-MM-AAAA`;
   cualquier otra cosa queda vacía sin avisar.

## Paso 3 — Previsualizar

**Base institucional → Cargar archivo**, elija el período, adjunte el archivo y
pulse **Previsualizar**.

No escribe nada en la base. Dice cuántas altas, cuántas actualizaciones y
cuántos errores saldrían, con el número de fila y el motivo de cada error.
Corrija el archivo y repita hasta que los errores sean los que espera.

## Paso 4 — Aplicar

El mismo formulario, botón **Aplicar carga**. Ahora sí escribe.

Es idempotente: volver a subir el mismo archivo actualiza, no duplica. Si se
equivocó en una columna, corrija el archivo y vuelva a aplicarlo.

Por cada fila válida el sistema crea o actualiza la persona, abre su expediente
si no lo tenía, pre-puebla la ficha socioeconómica y genera las alertas que
correspondan (violencia familiar a Trabajo Social, necesidad educativa especial
a Psicopedagogía, gestación y lactancia a Medicina, consumo declarado a
Psicología).

## Paso 5 — Verificar que quedó cargado

**Base institucional → Ver lo cargado**

Lista fila por fila. Busque por cédula, nombre, facultad o carrera, y ordene por
cualquier columna pulsando su cabecera (otra vez, para invertir el sentido).

Abajo, el historial de cargas con sus conteos: fecha, archivo, período, filas,
altas, actualizaciones y errores.

## Paso 6 — Comprobar el autocompletado

Es lo que la carga viene a alimentar, y conviene verificarlo con una cuenta de
profesional, no con la de administración.

1. Entre con un profesional, por ejemplo `jhoely.lalangui` / `jhoely.lalangui`.
2. **Expedientes** → escriba tres letras de un apellido que acabe de cargar en
   la casilla *Por nombre o apellido*. Deben aparecer sugerencias con la cédula
   y la carrera.
3. Escriba una cédula cargada en *Por cédula* y pulse **Buscar**: sale la
   tarjeta con facultad, carrera, ciclo y estado de matrícula, y el botón para
   abrir el expediente.

Si las sugerencias no salen, la carga no llegó: vuelva al paso 5.

## Registrar a varias personas de una vez

Distinto de la carga: **Expedientes → Varias cédulas** abre el expediente de una
lista de cédulas pegadas en fila, resolviéndolas contra lo que ya está cargado.
Sirve para preparar una jornada, no para alimentar el padrón.

## Preguntas que se repiten

**¿Puedo cargar sin ser administrador?** No. La pantalla exige el permiso
`academico.add_cargainstitucional`. La cuenta `1104346091` lo tiene; un
profesional corriente, no.

**¿Qué pasa con una cédula que no pasa el módulo 10?** La fila se rechaza y
queda anotada en la bitácora con su número de línea. El resto del archivo se
procesa igual.

**¿Y si el archivo trae otros nombres de encabezado?** No hay que renombrar
nada: el asistente permite mapear cada alias contra la columna canónica y
guarda ese mapeo con la carga.

**¿Se puede deshacer una carga?** No hay un botón para eso. Como es idempotente,
la vía es corregir el archivo y volver a aplicarlo. Por eso conviene
previsualizar siempre.
