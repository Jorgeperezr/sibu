"""
Carga la ficha socioeconómica (Excel/CSV) a la réplica institucional.

Uso:
    python manage.py cargar_ficha <archivo> --periodo 2026-1 [--dry-run]

Equivalente por consola del asistente web de 6 pasos (informe, sección 7.2).
"""
import os

from django.core.management.base import BaseCommand, CommandError

from apps.core.models import PeriodoAcademico

from ...models import CargaInstitucional
from ...services import LectorFicha, ProcesadorCarga, hash_archivo


class Command(BaseCommand):
    help = "Carga la ficha socioeconómica de matrícula (Excel/CSV) del período."

    def add_arguments(self, parser):
        parser.add_argument("archivo", type=str)
        parser.add_argument("--periodo", required=True, help="Código del período, ej. 2026-1")
        parser.add_argument("--dry-run", action="store_true", help="Valida sin aplicar cambios.")

    def handle(self, *args, **options):
        archivo = options["archivo"]
        if not os.path.exists(archivo):
            raise CommandError(f"No existe el archivo: {archivo}")
        try:
            periodo = PeriodoAcademico.objects.get(codigo=options["periodo"])
        except PeriodoAcademico.DoesNotExist as exc:
            raise CommandError(
                f"No existe el período {options['periodo']}. Créelo primero en el admin."
            ) from exc

        formato = "csv" if archivo.lower().endswith(".csv") else "xlsx"
        carga = CargaInstitucional.objects.create(
            periodo=periodo, nombre_archivo=os.path.basename(archivo),
            hash_archivo=hash_archivo(archivo), formato=formato,
        )
        lector = LectorFicha(archivo, formato)
        self.stdout.write(self.style.NOTICE(
            f"Procesando {carga.nombre_archivo} ({lector.total()} filas) — período {periodo.codigo}…"
        ))
        aplicar = not options["dry_run"]
        resultado = ProcesadorCarga(carga, carga.mapeo_columnas).procesar(lector, aplicar=aplicar)

        carga.total_filas = resultado.total
        carga.altas = resultado.altas
        carga.actualizaciones = resultado.actualizaciones
        carga.errores = resultado.errores
        carga.estado = (CargaInstitucional.Estado.VALIDADA if options["dry_run"]
                        else CargaInstitucional.Estado.APLICADA)
        carga.bitacora = resultado.as_dict()
        carga.save()

        self.stdout.write(self.style.SUCCESS(
            f"Total: {resultado.total} | Altas: {resultado.altas} | "
            f"Actualizaciones: {resultado.actualizaciones} | Errores: {resultado.errores} | "
            f"Alertas: {resultado.alertas_generadas}"
        ))
        if resultado.errores:
            self.stdout.write(self.style.WARNING("Primeros errores:"))
            for e in resultado.detalle_errores[:10]:
                self.stdout.write(f"  - {e}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry-run: no se aplicaron cambios."))
