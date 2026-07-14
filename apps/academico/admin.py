from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import CargaInstitucional, DatoAcademico


@admin.register(CargaInstitucional)
class CargaInstitucionalAdmin(admin.ModelAdmin):
    list_display = ("periodo", "nombre_archivo", "estado", "total_filas",
                    "altas", "actualizaciones", "errores", "creado_en")
    list_filter = ("estado", "periodo")
    readonly_fields = ("hash_archivo", "bitacora", "total_filas", "altas",
                       "actualizaciones", "errores")
    change_list_template = "admin/academico/carga_changelist.html"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["url_asistente"] = reverse("academico:asistente")
        return super().changelist_view(request, extra_context)


@admin.register(DatoAcademico)
class DatoAcademicoAdmin(admin.ModelAdmin):
    list_display = ("persona", "periodo", "facultad", "carrera", "ciclo",
                    "jornada", "estado")
    list_filter = ("periodo", "facultad", "modalidad", "jornada", "estado")
    search_fields = ("persona__cedula", "persona__nombres", "persona__apellidos")
    autocomplete_fields = ("persona",)
