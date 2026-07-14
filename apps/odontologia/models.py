"""Historia clínica odontológica con odontograma FDI (informe 6.3)."""
from django.db import models

from apps.expediente.models import Atencion


class AtencionOdontologia(models.Model):
    atencion = models.OneToOneField(
        Atencion, on_delete=models.CASCADE, primary_key=True, related_name="odontologia"
    )
    examen_estomatognatico = models.JSONField(default=dict, blank=True)
    indices = models.JSONField(default=dict, blank=True, help_text="CPO-D, placa, periodontal")
    plan_tratamiento = models.TextField(blank=True)

    class Meta:
        verbose_name = "atención de odontología"
        verbose_name_plural = "atenciones de odontología"


class OdontogramaDetalle(models.Model):
    class TipoRegistro(models.TextChoices):
        INICIAL = "inicial", "Inicial"
        EVOLUCION = "evolucion", "Evolución"

    atencion = models.ForeignKey(Atencion, on_delete=models.CASCADE, related_name="odontograma")
    pieza_fdi = models.CharField(max_length=2, help_text="Notación FDI de dos dígitos")
    superficie = models.CharField(max_length=2, blank=True)
    estado_codigo = models.CharField(max_length=20)
    tipo = models.CharField(max_length=10, choices=TipoRegistro.choices, default=TipoRegistro.INICIAL)
    observacion = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "detalle de odontograma"
        verbose_name_plural = "detalles de odontograma"
