"""
Ficha socioeconómica y gestión de casos (informe 6.8). La ficha se pre-puebla
automáticamente desde la ficha de matrícula (informe 7.3) y el profesional la
verifica y complementa.
"""

from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion, Expediente


class FichaSocioeconomica(ModeloBase):
    class Origen(models.TextChoices):
        MATRICULA = "matricula", "Pre-poblada desde matrícula"
        VERIFICADA = "verificada_ts", "Verificada por Trabajo Social"

    expediente = models.ForeignKey(
        Expediente, on_delete=models.PROTECT, related_name="fichas_socio"
    )
    version = models.PositiveSmallIntegerField(default=1)
    vigente = models.BooleanField(default=True)
    origen = models.CharField(max_length=14, choices=Origen.choices, default=Origen.MATRICULA)

    ingresos = models.JSONField(default=dict, blank=True)
    egresos = models.JSONField(default=dict, blank=True)
    ingresos_totales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    egresos_totales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vivienda_estudiante = models.JSONField(default=dict, blank=True)
    vivienda_familiar = models.JSONField(default=dict, blank=True)
    convivencia = models.JSONField(default=dict, blank=True)
    situacion_laboral = models.JSONField(default=dict, blank=True)
    salud_familiar = models.JSONField(default=dict, blank=True)
    puntaje = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    estrato = models.CharField(max_length=30, blank=True)

    class Meta:
        verbose_name = "ficha socioeconómica"
        verbose_name_plural = "fichas socioeconómicas"


class VisitaDomiciliaria(models.Model):
    atencion = models.ForeignKey(Atencion, on_delete=models.CASCADE, related_name="visitas")
    fecha = models.DateField()
    condiciones_verificadas = models.JSONField(default=dict, blank=True)
    georreferencia = models.JSONField(default=dict, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "visita domiciliaria"
        verbose_name_plural = "visitas domiciliarias"

    def __str__(self):
        return f"Visita {self.fecha:%d/%m/%Y} — {self.atencion}"
