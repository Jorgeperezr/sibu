# Estado del proyecto SIBU — cierre de esta etapa

Este documento cierra el desarrollo de SIBU en este repositorio. Dice qué hay
construido, qué está comprobado y con qué se verifica, para que quien lo retome
—o quien lo audite— no tenga que reconstruirlo leyendo 88 commits.

El desarrollo continúa en `sibu_local`, una versión portable del mismo sistema.

## Qué es

Sistema Integral de Bienestar Universitario de la Universidad Nacional de Loja.
Django 5.1 + DRF + PostgreSQL 16 + Bootstrap 5.

**Nueve servicios** —Medicina, Enfermería, Odontología, Laboratorio, Farmacia,
Psicología, Psicopedagogía, Trabajo Social y Becas— sobre un **expediente
único**, más citas, derivaciones, firma, talleres, portal del estudiante,
carga de la base institucional, informes y tablero de gestión.

22 aplicaciones, 66 migraciones, 110 archivos de prueba.

## Lo que no se negocia

Las reglas del dominio están en `CLAUDE.md` y se repiten aquí las dos que
condicionan todo lo demás:

- **El sello de Psicología es absoluto.** Su contenido clínico no sale del
  servicio: ni Dirección, ni administración, ni break-glass. Cada cambio que
  tocó RBAC, derivaciones, firma, portal o reportes se comprobó contra esto.
- **Los tableros muestran gestión, no contenido.** Bajo cinco pacientes
  distintos, un conteo identifica: se reporta `<5`.

## Cómo se verifica

Los cinco comandos, **por separado** —el `&&` oculta el fallo de formato y
tumba el CI—:

```
ruff check .
ruff format --check .
pytest apps -q          # 1236 al cierre, deben pasar TODAS
python manage.py check
python manage.py makemigrations --check --dry-run
```

## Cómo se levanta

```
make up
```

Eso basta, también después de un `git pull`: compara lo que hay en la base con
lo que el código define y decide solo si hay que migrar o volver a sembrar.
`make cuentas` recuerda las credenciales de prueba.

## Cómo se despliega

`docs/ORACLE_CLOUD.md`, probado de punta a punta sobre la pila real —gunicorn
tras nginx con TLS—. Las dos trampas que hacen perder una tarde están
documentadas ahí: hay **dos cortafuegos** en la imagen de Ubuntu de Oracle, y
`docker compose` **no lee `.env.prod`** para sus propias variables sin
`--env-file`.

Después de desplegar:

```
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  exec web python manage.py createsuperuser
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  exec web python manage.py ensayo_despliegue --usuario X --clave Y
```

`ensayo_despliegue` no mira la configuración: la **ejercita**. Envía el
formulario de acceso, porque el fallo más caro del despliegue —un
`CSRF_TRUSTED_ORIGINS` mal puesto— deja el sitio en pie, todas las páginas
respondiendo 200 y a todo el mundo fuera.

## Método

Tres disciplinas que explican por qué el código está como está, y que conviene
conservar:

1. **Reproducir antes de arreglar.** Cada defecto se demostró primero.
2. **Falsificar después de arreglar.** Se rompe la guarda a propósito y se
   comprueba que la prueba falla señalando el defecto. Si NO falla, el fallo
   está en la prueba: pasó, y se reescribió la prueba.
3. **Mirar la pantalla.** La mayoría de los defectos de las últimas tandas
   responden 200 con el contexto correcto y mienten al imprimir. Ninguna prueba
   de estado los ve. Se encontraron recorriendo el sistema con un navegador.

`CLAUDE.md` recoge, una por una, las trampas que ya costaron caro. Leerlo antes
de tocar nada ahorra repetirlas.

## Lo que queda abierto

Honestamente, para que nadie lo descubra tarde:

- **Los anexos documentales no se cifran.** `DocumentoAnexo.ruta_cifrada` nombra
  algo que no existe: el proyecto no tiene dependencia de cifrado. O se abre un
  sprint de cifrado en reposo, o se renombra el campo para que no prometa lo
  que no hace.
- **Nueve de los diez profesionales no tienen horario**, así que no se les puede
  reservar cita. Lo declara cada uno desde *Mi horario*; hasta que lo hagan, la
  agenda está vacía por configuración, no por un fallo.
- **Coordinador de Sección y Personal Administrativo** están definidos como
  roles y no hay ninguna cuenta con ellos.
- **La gestión de perfiles asigna, no crea cuentas.** Dar de alta una cuenta
  nueva sigue siendo `/admin/` de Django.
- **FirmaEC queda descartado** en favor de firma electrónica simple: SIBU genera
  el PDF, el profesional lo firma en su equipo y decide si lo sube. El código de
  FirmaEC se conserva tras un provider y se elige con `FIRMA_PROVIDER=firmaec`.
