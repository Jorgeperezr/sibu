"""Ficha de enfermería y signos vitales reutilizables por Medicina (informe 6.2)."""
from django.db import models

from apps.expediente.models import Atencion
from apps.usuarios.models import PerfilProfesional


class SignosVitales(models.Model):
    atencion = models.ForeignKey(Atencion, on_delete=models.CASCADE, related_name="signos_vitales")
    fecha_hora = models.DateTimeField(auto_now_add=True)
    temperatura = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    fc = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="frecuencia cardíaca")
    fr = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="frecuencia respiratoria")
    pa_sistolica = models.PositiveSmallIntegerField(null=True, blank=True)
    pa_diastolica = models.PositiveSmallIntegerField(null=True, blank=True)
    sat_o2 = models.PositiveSmallIntegerField(null=True, blank=True)
    peso = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    talla = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    imc = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    glicemia_capilar = models.PositiveSmallIntegerField(null=True, blank=True)
    responsable = models.ForeignKey(PerfilProfesional, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "signos vitales"
        verbose_name_plural = "signos vitales"


class ProcedimientoEnfermeria(models.Model):
    atencion = models.OneToOneField(
        Atencion, on_delete=models.CASCADE, primary_key=True, related_name="enfermeria"
    )
    procedimientos = models.JSONField(default=list, blank=True)
    inmunizaciones = models.JSONField(default=list, blank=True)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = "atención de enfermería"
        verbose_name_plural = "atenciones de enfermería"
