"""
Ficha psicológica con confidencialidad reforzada (informe 6.6, 10.2).
El contenido de sesión es visible solo para el profesional tratante; el resto
del sistema ve únicamente la existencia de la atención.
"""

from django.db import models

from apps.expediente.models import Atencion


class FichaPsicologica(models.Model):
    atencion = models.OneToOneField(
        Atencion, on_delete=models.CASCADE, primary_key=True, related_name="psicologia"
    )
    # Campos sensibles: se cifran a nivel de aplicación (ver apps.core cifrado)
    motivo = models.TextField(blank=True)
    historia_problema = models.TextField(blank=True)
    estado_mental = models.JSONField(default=dict, blank=True)
    impresion_diagnostica = models.CharField(max_length=255, blank=True)
    plan_terapeutico = models.TextField(blank=True)
    riesgo_nivel = models.CharField(
        max_length=10,
        choices=[("bajo", "Bajo"), ("medio", "Medio"), ("alto", "Alto")],
        default="bajo",
        help_text="Riesgo alto dispara protocolo de alerta al coordinador.",
    )

    class Meta:
        verbose_name = "ficha psicológica"
        verbose_name_plural = "fichas psicológicas"

    def __str__(self):
        return f"Ficha psicológica: {self.atencion}"


class SesionPsicologica(models.Model):
    ficha = models.ForeignKey(FichaPsicologica, on_delete=models.CASCADE, related_name="sesiones")
    numero = models.PositiveSmallIntegerField()
    fecha = models.DateField()
    temas = models.TextField(blank=True)
    tecnicas = models.CharField(max_length=255, blank=True)
    evolucion = models.TextField(blank=True)
    proxima_sesion = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "sesión psicológica"
        verbose_name_plural = "sesiones psicológicas"
        ordering = ["numero"]

    def __str__(self):
        return f"Sesión {self.numero} — {self.fecha:%d/%m/%Y}"


class AplicacionEscala(models.Model):
    ficha = models.ForeignKey(FichaPsicologica, on_delete=models.CASCADE, related_name="escalas")
    escala = models.CharField(max_length=120)
    puntaje = models.CharField(max_length=40, blank=True)
    interpretacion = models.CharField(max_length=255, blank=True)
    fecha = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.escala}: {self.puntaje}"
