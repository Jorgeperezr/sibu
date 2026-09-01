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

## Trampas técnicas que ya nos costaron caro

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
- **Comentarios de plantilla `{# #}` solo funcionan en una línea.** Para varias,
  `{% comment %}`.
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
