"""
Deja la base lista para trabajar, con un solo comando.

Antes había que recordar y teclear cinco comandos en el orden correcto
—`migrate`, `seed_inicial`, `configurar_rbac`, `cargar_cie10`,
`createsuperuser`— y si uno se saltaba, el síntoma aparecía más tarde y en otro
sitio: sin `seed_inicial` no hay servicios y las bandejas salen vacías; sin
`configurar_rbac` los grupos existen sin permisos; sin una cuenta creada, la
pantalla de inicio de sesión rechaza todo lo que se escriba en ella.

    python manage.py preparar          # todo, con datos de demostración
    python manage.py preparar --sin-demo

Es idempotente: cada paso que compone se puede repetir sin duplicar nada, así
que volver a ejecutarlo sobre una base ya preparada es seguro.

En producción (`DEBUG=False`) hace los cuatro primeros pasos —que son
exactamente el arranque correcto de un despliegue— y omite los datos de
demostración, igual que haría `datos_demo` por su cuenta.
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Migraciones, datos base, RBAC, catálogo CIE-10 y cuentas de prueba."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sin-demo",
            action="store_true",
            dest="sin_demo",
            help="No sembrar usuarios ni pacientes de demostración.",
        )

    def handle(self, *args, **opciones):
        detalle = opciones.get("verbosity", 1)
        pasos = [
            ("Aplicando migraciones", "migrate", {"interactive": False}),
            ("Cargando secciones, servicios y roles", "seed_inicial", {}),
            ("Configurando permisos por rol", "configurar_rbac", {}),
            ("Cargando el catálogo CIE-10", "cargar_cie10", {}),
        ]
        # Los datos de demostración traen contraseñas conocidas y pacientes
        # inventados: en un servidor real serían una puerta abierta con
        # historias clínicas falsas dentro del expediente único.
        sembrar_demo = not opciones["sin_demo"] and settings.DEBUG

        total = len(pasos) + (1 if sembrar_demo else 0)
        for numero, (titulo, comando, extra) in enumerate(pasos, start=1):
            if detalle:
                self.stdout.write(f"[{numero}/{total}] {titulo}...")
            call_command(comando, verbosity=detalle, **extra)

        if sembrar_demo:
            if detalle:
                self.stdout.write(f"[{total}/{total}] Sembrando datos de prueba...")
            # `datos_demo` termina imprimiendo las credenciales, que es lo único
            # de toda la preparación que hay que leer; por eso no se silencia
            # salvo que quien llama pida silencio explícitamente.
            call_command("datos_demo", verbosity=detalle)
        elif not detalle:
            return
        elif opciones["sin_demo"]:
            self.stdout.write(self.style.SUCCESS("\nBase preparada, sin datos de demostración."))
            self.stdout.write("Cree una cuenta con: python manage.py createsuperuser")
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nBase preparada. Los datos de demostración se omiten con DEBUG=False."
                )
            )
            self.stdout.write("Cree una cuenta con: python manage.py createsuperuser")
