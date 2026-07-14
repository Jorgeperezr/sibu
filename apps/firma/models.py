"""Firma electrónica/digital de documentos clínicos (informe 5.2 M18, 14.4)."""
from django.db import models

from apps.usuarios.models import Usuario


class FirmaDocumento(models.Model):
    class TipoFirma(models.TextChoices):
        ELECTRONICA = "electronica", "Electrónica simple"
        DIGITAL = "digital_certificado", "Digital con certificado"

    documento_ref_tipo = models.CharField(max_length=40, help_text="Modelo firmado (p. ej. atencion, receta).")
    documento_ref_id = models.PositiveBigIntegerField()
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="firmas")
    tipo_firma = models.CharField(max_length=20, choices=TipoFirma.choices)
    hash_documento = models.CharField(max_length=64)
    sello_tiempo = models.DateTimeField(auto_now_add=True)
    certificado_serial = models.CharField(max_length=120, blank=True)
    valida = models.BooleanField(default=True)

    class Meta:
        verbose_name = "firma de documento"
        verbose_name_plural = "firmas de documentos"
        indexes = [models.Index(fields=["documento_ref_tipo", "documento_ref_id"])]
