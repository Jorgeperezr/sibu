"""Historia clínica médica: extensión 1:1 de Atencion (informe 6.1)."""
from django.db import models

from apps.core.models import CIE10
from apps.expediente.models import Atencion


class AtencionMedicina(models.Model):
    atencion = models.OneToOneField(
        Atencion, on_delete=models.CASCADE, primary_key=True, related_name="medicina"
    )
    enfermedad_actual = models.TextField(blank=True)
    revision_sistemas = models.JSONField(default=dict, blank=True)
    examen_fisico = models.JSONField(default=dict, blank=True)
    plan_tratamiento = models.TextField(blank=True)
    indicaciones = models.TextField(blank=True)
    dias_reposo = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "atención de medicina"
        verbose_name_plural = "atenciones de medicina"


class Diagnostico(models.Model):
    class TipoDx(models.TextChoices):
        PRESUNTIVO = "presuntivo", "Presuntivo"
        DEFINITIVO = "definitivo", "Definitivo"

    atencion = models.ForeignKey(Atencion, on_delete=models.CASCADE, related_name="diagnosticos")
    cie10 = models.ForeignKey(CIE10, on_delete=models.PROTECT)
    tipo = models.CharField(max_length=12, choices=TipoDx.choices, default=TipoDx.PRESUNTIVO)
    principal = models.BooleanField(default=True)

    class Meta:
        verbose_name = "diagnóstico"
        verbose_name_plural = "diagnósticos"

    def __str__(self):
        return f"{self.cie10_id} ({self.get_tipo_display()})"
