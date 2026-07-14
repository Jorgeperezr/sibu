# Plan de Sprints — SIBU

Desarrollo incremental por sprints de 2 semanas, alineado al cronograma del
informe técnico (sección 17). Cada sprint entrega funcionalidad usable, probada
y desplegable.

| Sprint | Módulo / Objetivo | Estado |
|--------|-------------------|--------|
| **S1** | `academico` — carga de la ficha socioeconómica (Excel/CSV) | ✅ Entregado |
| S2 | `expediente` + `usuarios` — expediente único, RBAC, consulta por cédula en UI | Pendiente |
| S3 | `citas` — agenda y ciclo de vida de la cita | Pendiente |
| S4 | `enfermeria` + `medicina` — triaje, HC médica, recetas y órdenes | Pendiente |
| S5 | `laboratorio` — órdenes, resultados y envío al correo institucional | Pendiente |
| S6 | `odontologia` + `farmacia` — odontograma, despacho e inventario | Pendiente |
| S7 | `psicologia` + `psicopedagogia` + `trabajo_social` + `derivaciones` | Pendiente |
| S8 | `becas` (fase 1) + `talleres` (Google Drive) + portal de autogestión | Pendiente |
| S9 | `reportes` + tableros + indicadores | Pendiente |
| S10 | Endurecimiento, pruebas de carga/penetración, piloto | Pendiente |

## Convención de ramas y commits

- Rama por sprint: `sprint/NN-modulo` → PR a `develop` → `main` al cerrar.
- Commits: `feat(academico): asistente de carga`, `test(...)`, `fix(...)`, `docs(...)`.
- Definición de "terminado": código + pruebas (cobertura del módulo ≥ 80 %) +
  `manage.py check` sin errores + documentación del sprint + CI en verde.
