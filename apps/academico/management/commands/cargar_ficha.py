"""
Carga la ficha socioeconómica (Excel/CSV) a la réplica institucional.

Uso:
    python manage.py cargar_ficha <archivo> --periodo 2026-1 [--dry-run]

Este comando es el equivalente por consola del asistente web de 6 pasos
descrito en la sección 7.2 del informe. Aquí se deja el esqueleto con los
puntos de extensión (mapeo, validación, upsert) marcados como TODO.
"""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Carga la ficha socioeconómica de matrícula (Excel/CSV) del período."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str)
        parser.add_argument("--periodo", required=True, help="Código del período, ej. 2026-1")
        parser.add_argument("--dry-run", action="store_true", help="Valida sin aplicar cambios.")

    def handle(self, *args, **options):
        archivo = options["archivo"]
        periodo = options["periodo"]
        self.stdout.write(self.style.NOTICE(f"Leyendo {archivo} para el período {periodo}…"))
        # TODO: 1) leer con pandas/openpyxl
        # TODO: 2) mapear columnas contra la plantilla oficial
        # TODO: 3) validar (cédula, correo, catálogos, duplicados)
        # TODO: 4) upsert por (cedula, periodo) en DatoAcademico + pre-poblar fichas
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run: no se aplicaron cambios."))
        raise CommandError("Implementación pendiente (esqueleto inicial).")
