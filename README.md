# SIBU — Sistema Integral de Bienestar Universitario (UNL)

Plataforma web institucional para la administración unificada de los servicios
de la Unidad de Bienestar Universitario de la **Universidad Nacional de Loja**:
Medicina, Enfermería, Odontología, Laboratorio Clínico, Farmacia, Psicología,
Psicopedagogía, Trabajo Social y Becas.

> Documento base funcional y técnico: `docs/Informe_Tecnico_SIBU_UNL.md`.

## Stack

- **Backend:** Python 3.12 · Django 5 · Django REST Framework
- **Base de datos:** PostgreSQL 16
- **Frontend:** HTML5 · CSS3 · JavaScript · Bootstrap 5
- **Asíncrono:** Celery + Redis
- **Entorno de desarrollo:** GitHub Codespaces → macOS Intel (dev container)

## Arranque rápido (Codespaces o VS Code + Dev Containers)

1. Abrir el repositorio en un Codespace (o *Reopen in Container* en VS Code).
2. El contenedor instala dependencias y aplica migraciones automáticamente.
3. Copiar variables: `cp .env.example .env` y ajustar lo necesario.
4. Cargar datos base y crear un administrador:

   ```bash
   python manage.py seed_inicial
   python manage.py createsuperuser
   python manage.py runserver 0.0.0.0:8000
   ```

5. Abrir el puerto 8000 reenviado. API: `/api/docs/` · Admin: `/admin/`.

## Comandos útiles (Makefile)

| Comando        | Acción                                   |
|----------------|------------------------------------------|
| `make run`     | Servidor de desarrollo                   |
| `make worker`  | Celery worker + beat                     |
| `make test`    | Pruebas con cobertura                    |
| `make lint`    | Ruff + Bandit                            |
| `make seed`    | Secciones, servicios y roles iniciales   |

## Estructura

```
config/            Configuración (settings por ambiente, urls, celery)
apps/              Apps de dominio (core, usuarios, academico, expediente,
                   servicios clínicos, becas, talleres, transversales)
api/v1/            Capa REST (routers, endpoints)
templates/ static/ Frontend (Bootstrap 5)
docs/              Informe técnico y documentación
.devcontainer/     Entorno reproducible (Codespaces / macOS)
```

## Seguridad

Sistema con datos de salud y académicos sensibles: MFA, RBAC por servicio,
cifrado de campos, auditoría inmutable y buenas prácticas OWASP. No cargar
datos reales en entornos de desarrollo.

## Hoja de ruta (fases)

- **Fase 1:** base institucional por carga Excel/CSV, servicios clínicos,
  becas (beneficiarios + seguimiento), talleres con evidencias en Google Drive.
- **Fase 2:** integración API con el SGA y con el sistema de becas institucional.
