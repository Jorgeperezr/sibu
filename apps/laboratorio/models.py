"""
Órdenes y resultados de laboratorio. Solo Medicina y Odontología pueden crear
órdenes (regla de negocio, informe 5.2). El resultado validado se envía al
correo institucional del paciente (informe 5.2, 12.4).
"""
from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion
from apps.usuarios.models import PerfilProfesional


class Examen(models.Model):
    """Catálogo de exámenes con valores de referencia por parámetro."""

    codigo = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=150)
    perfil = models.CharField(max_length=80, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "examen"
        verbose_name_plural = "catálogo de exámenes"

    def __str__(self):
        return self.nombre


class OrdenLaboratorio(ModeloBase):
    class Estado(models.TextChoices):
        CREADA = "creada", "Creada"
        MUESTRA_TOMADA = "muestra_tomada", "Muestra tomada"
        EN_PROCESO = "en_proceso", "En proceso"
        RESULTADO = "resultado", "Resultado registrado"
        VALIDADO = "validado", "Validado"
        PUBLICADO = "publicado", "Publicado"
        ANULADA = "anulada", "Anulada"
        RECHAZADA = "rechazada", "Muestra rechazada"

    atencion = models.ForeignKey(Atencion, on_delete=models.PROTECT, related_name="ordenes_lab")
    prioridad = models.CharField(
        max_length=10, choices=[("rutina", "Rutina"), ("urgente", "Urgente")], default="rutina"
    )
    diagnostico_presuntivo = models.CharField(max_length=255, blank=True)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.CREADA)
    responsable_toma = models.ForeignKey(
        PerfilProfesional, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    enviado_correo_paciente = models.BooleanField(default=False)

    class Meta:
        verbose_name = "orden de laboratorio"
        verbose_name_plural = "órdenes de laboratorio"


class OrdenExamen(models.Model):
    orden = models.ForeignKey(OrdenLaboratorio, on_delete=models.CASCADE, related_name="examenes")
    examen = models.ForeignKey(Examen, on_delete=models.PROTECT)


class ResultadoParametro(models.Model):
    class Marcador(models.TextChoices):
        NORMAL = "normal", "Normal"
        ALTO = "alto", "Alto"
        BAJO = "bajo", "Bajo"
        CRITICO = "critico", "Crítico"

    orden_examen = models.ForeignKey(OrdenExamen, on_delete=models.CASCADE, related_name="resultados")
    parametro = models.CharField(max_length=120)
    valor = models.CharField(max_length=60)
    unidad = models.CharField(max_length=30, blank=True)
    ref_min = models.CharField(max_length=30, blank=True)
    ref_max = models.CharField(max_length=30, blank=True)
    marcador = models.CharField(max_length=10, choices=Marcador.choices, default=Marcador.NORMAL)
    validado_por = models.ForeignKey(
        PerfilProfesional, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    validado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "resultado de parámetro"
        verbose_name_plural = "resultados de parámetros"
