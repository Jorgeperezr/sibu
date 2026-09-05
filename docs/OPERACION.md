# Operación diaria

Qué se ejecuta, cuándo y qué significa lo que responde. Para el despliegue en
servidor, `DESPLIEGUE.md`; para cargar la base institucional,
`COMO_CARGAR_LA_BASE.md`.

## Los comandos

| Comando | Cuándo |
|---|---|
| `make up` | Arrancar. También después de un `git pull`: decide solo si hay que migrar o resembrar. |
| `make cuentas` | Recordar con qué usuario entrar. |
| `make revisar` | Buscar incoherencias en los datos. Antes de migrar en un servidor con datos, y cuando algo no cuadre. |
| `make test` | Las pruebas con cobertura. |
| `make lint` | `ruff check`, `ruff format --check` y `bandit`, **separados**: el `&&` oculta el fallo de formato y tumba el CI. |
| `make demo` | Resembrar datos de prueba. Solo con `DEBUG=True`. |

## `make up` no necesita ayuda

`preparar --si-cambio` compara lo que hay en la base con lo que el código
define y decide por su cuenta. Prepara si:

- la base está vacía o no tiene tablas;
- hay migraciones sin aplicar;
- **cambió el contenido de los comandos de siembra** —`datos_demo`,
  `seed_inicial`, `cargar_cie10`, `configurar_rbac`—, que es lo que pasa tras
  un `git pull` que trae cuentas o servicios nuevos.

La huella es del contenido y no de la fecha: `git pull` reescribe fechas aunque
el contenido sea idéntico, y por fecha se resembraría en cada arranque. Se
anota al final, así que un paso que reviente deja la base marcada como
pendiente y el arranque siguiente vuelve a intentarlo.

Antes esto obligaba a acordarse de `make demo` a mano, y no acordarse se
parecía mucho a «las credenciales no funcionan».

## `revisar_datos`: qué comprueba y por qué

Las restricciones de base de datos impiden escribir un disparate **nuevo**,
pero no dicen nada de lo escrito antes de existir ellas: una fila anterior
sobrevive a la migración si nadie la toca. Y hay invariantes que ninguna
restricción puede expresar, porque cruzan dos tablas.

| Comprobación | Qué significa si salta |
|---|---|
| Cédulas que no pasan el módulo 10 | Se validan al guardar desde el Sprint 10; estas son anteriores. |
| Atenciones con un tratante de otro servicio | Quien consta de tratante **puede verla**, sello incluido. |
| Lotes cuyo saldo no cuadra con sus movimientos | Un movimiento perdido o un ajuste sin registrar. Es la que delata la escritura perdida que se corrigió con `select_for_update`. |
| Dos fichas socioeconómicas vigentes | De la vigente salen el puntaje y el estrato con los que se resuelve una beca. Hoy lo impide un índice único: esta comprobación solo puede saltar **antes** de migrar. |
| Derivaciones atendidas sin atención de destino | Consta como atendida y no hay registro de qué se hizo. |
| Citas con un profesional de otro servicio | El paciente llega y quien lo espera no atiende ese servicio. |
| Personas con más de un expediente | El expediente es único por persona: dos parten su historia en dos. |
| Alertas clínicas sin persona detrás | Una alerta que no apunta a nadie no avisa a nadie. |
| Entradas de bitácora clínicas sin servicio declarado | La pantalla no puede velarlas y mostraría al paciente de un servicio sellado. |

**No corrige nada, y es a propósito.** Un descuadre de inventario puede ser un
movimiento perdido o un ajuste sin registrar, y cada caso se arregla distinto.
Decidirlo por su cuenta convertiría un descuadre visible en uno silencioso.

Devuelve código de salida 1 si encuentra algo, para encadenarlo en un guion de
despliegue.

## La bitácora

**Gestión → Bitácora** responde «quién abrió esto y cuándo». Registra cada
lectura de contenido clínico y **cada intento rechazado**, que es la consulta
que más se va a hacer: el botón *Solo intentos rechazados* los aísla.

La abre Dirección, Coordinación y administración. Un servicio confidencial ve
además sus propias entradas, para poder auditarse: nadie de fuera puede revisar
su trabajo, así que sin eso quedaría sin control ninguno. Un profesional
corriente no la abre —recorrerla entera diría quién pasó por cada servicio—.

De una entrada de un servicio confidencial se ve **quién** accedió y cuándo, no
**sobre quién**: la identidad del paciente es lo que el sello protege, y una
bitácora no es una excepción.

## Agendamiento

Tres pantallas, y cada una responde una pregunta distinta:

- **Calendario** (`/citas/calendario/`) — en qué días del mes hay algo. Da
  conteos, nunca el paciente ni el motivo: un calendario que imprimiera el
  nombre haría innecesario abrir el día y con eso se saltaría el control que
  vive en la agenda. Las canceladas no cuentan.
- **Agenda del día** (`/citas/`) — el detalle de un día: paciente, servicio,
  estado, y las acciones de marcar llegada, reprogramar y cancelar.
- **Reservar** (`/citas/reservar/`) — cédula → servicio → profesional → fecha →
  turno. Los turnos los genera la `Agenda` del profesional para el día de la
  semana que toque, descontando las citas vivas y los bloqueos que solapen. Si
  la casilla sale vacía: ese día no hay agenda vigente para ese servicio, está
  llena, o está bloqueada.

Ver la agenda o el calendario de **otro** profesional exige compartir servicio
con él. No `is_staff`, que es una bandera del panel de Django y no dice nada
sobre el servicio: con ella se leía la agenda de Psicología.

La pantalla de cancelación **exige motivo escrito**; el servicio lo admite
vacío, así que quien llame a `services.cancelar` desde código debe pasarlo. Se
guarda explícitamente en `observaciones`: durante un tiempo se asignaba antes
de delegar en `cambiar_estado`, que guarda con un `update_fields` donde ese
campo no está, y Django lo descartaba sin avisar. Toda cancelación quedaba sin
causa registrada.

## Rendimiento

Las consultas de cada pantalla se midieron con 12 y con 52 pacientes: ninguna
crece con el número de filas. El padrón sube en una, que es el `COUNT` de la
paginación.

Si añade una pantalla que liste algo, mídalo igual —cargar la lista con datos
y contar consultas— antes que optimizar por intuición. Y use `select_related`
para las claves foráneas que la plantilla vaya a tocar: el N+1 aparece al
pintar, no al consultar.

## Cuando algo va mal

| Síntoma | Dónde mirar |
|---|---|
| «Usuario o contraseña incorrectos» con una cuenta que debería existir | `make cuentas`. Si falta, `make preparar`. |
| «La verificación CSRF ha fallado» | Arrancó con `make run` en vez de `make up`, o está en una rama sin el arreglo. La propia pantalla dice qué Origin llegó y cuáles acepta. |
| Un número que no cuadra en farmacia | `make revisar`. |
| Una pantalla vacía que debería tener datos | Compruebe el rol: `atenciones_visibles` devuelve cero a los administradores por separación de funciones, y eso es deliberado. `SEGURIDAD.md` lo explica. |
| El puerto 8000 ocupado | `kill $(lsof -ti:8000)` y repita `make up`. |
