"""Agenda por profesional y ciclo de vida de la cita (informe 5.2, 12.1)."""
from django.db import models

from apps.core.models import ModeloBase, Servicio
from apps.expediente.models import Expediente
from apps.usuarios.models import PerfilProfesional


class Agenda(ModeloBase):
    profesional = models.ForeignKey(PerfilProfesional, on_delete=models.CASCADE, related_name="agendas")
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT)
    dia_semana = models.PositiveSmallIntegerField(help_text="0=lunes … 6=domingo")
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    duracion_turno_min = models.PositiveSmallIntegerField(default=20)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "agenda"
        verbose_name_plural = "agendas"


class Cita(ModeloBase):
    class Estado(models.TextChoices):
        RESERVADA = "reservada", "Reservada"
        CONFIRMADA = "confirmada", "Confirmada"
        EN_ESPERA = "en_espera", "En espera"
        EN_ATENCION = "en_atencion", "En atención"
        ATENDIDA = "atendida", "Atendida"
        NO_ASISTIO = "no_asistio", "No asistió"
        CANCELADA = "cancelada", "Cancelada"
        REPROGRAMADA = "reprogramada", "Reprogramada"

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="citas")
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT)
    profesional = models.ForeignKey(PerfilProfesional, on_delete=models.PROTECT, related_name="citas")
    fecha_hora = models.DateTimeField(db_index=True)
    estado = models.CharField(max_length=14, choices=Estado.choices, default=Estado.RESERVADA)
    motivo = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "cita"
        verbose_name_plural = "citas"
        ordering = ["fecha_hora"]

    def __str__(self):
        return f"Cita {self.servicio} — {self.fecha_hora:%Y-%m-%d %H:%M}"
