"""
Agenda y ciclo de vida de la cita (informe, secciones 5.2 M05 y 12.1).

Estados canónicos (Anexo A):
    reservada → confirmada → en_espera → en_atencion → atendida
    (con transiciones a no_asistio | cancelada | reprogramada)
"""
from datetime import datetime, time, timedelta

from django.db import models
from django.utils import timezone

from apps.core.models import ModeloBase, Servicio
from apps.expediente.models import Expediente
from apps.usuarios.models import PerfilProfesional


class DiaSemana(models.IntegerChoices):
    LUNES = 0, "Lunes"
    MARTES = 1, "Martes"
    MIERCOLES = 2, "Miércoles"
    JUEVES = 3, "Jueves"
    VIERNES = 4, "Viernes"
    SABADO = 5, "Sábado"
    DOMINGO = 6, "Domingo"


class Agenda(ModeloBase):
    """
    Configuración de disponibilidad recurrente de un profesional en un servicio.

    Un profesional puede tener varias agendas (una por día/franja/servicio).
    Los turnos concretos se calculan a partir de estas franjas.
    """

    profesional = models.ForeignKey(
        PerfilProfesional, on_delete=models.CASCADE, related_name="agendas"
    )
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name="agendas")
    dia_semana = models.PositiveSmallIntegerField(choices=DiaSemana.choices)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    duracion_turno_min = models.PositiveSmallIntegerField(default=20)
    vigente_desde = models.DateField(default=timezone.localdate)
    vigente_hasta = models.DateField(null=True, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "agenda"
        verbose_name_plural = "agendas"
        ordering = ["profesional", "dia_semana", "hora_inicio"]

    def __str__(self):
        return (f"{self.profesional} · {self.get_dia_semana_display()} "
                f"{self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M}")

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.hora_inicio >= self.hora_fin:
            raise ValidationError("La hora de inicio debe ser anterior a la hora de fin.")

    def generar_turnos(self, fecha):
        """Genera la lista de horarios de inicio para un día concreto."""
        tz = timezone.get_current_timezone()
        turnos, actual = [], datetime.combine(fecha, self.hora_inicio, tzinfo=tz)
        fin = datetime.combine(fecha, self.hora_fin, tzinfo=tz)
        paso = timedelta(minutes=self.duracion_turno_min)
        while actual + paso <= fin:
            turnos.append(actual)
            actual += paso
        return turnos


class BloqueoAgenda(ModeloBase):
    """
    Bloqueos puntuales (vacaciones, reuniones, capacitaciones) que anulan la
    disponibilidad recurrente de la agenda en un rango de fechas/horas.
    """

    profesional = models.ForeignKey(
        PerfilProfesional, on_delete=models.CASCADE, related_name="bloqueos"
    )
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    motivo = models.CharField(max_length=200)

    class Meta:
        verbose_name = "bloqueo de agenda"
        verbose_name_plural = "bloqueos de agenda"
        ordering = ["-fecha_inicio"]


class Cita(ModeloBase):
    """
    Cita agendada. La lógica de transición de estado vive en `services.py`
    (patrón: no permitir cambios inválidos, dejar trazabilidad).
    """

    class Estado(models.TextChoices):
        RESERVADA = "reservada", "Reservada"
        CONFIRMADA = "confirmada", "Confirmada"
        EN_ESPERA = "en_espera", "En espera"
        EN_ATENCION = "en_atencion", "En atención"
        ATENDIDA = "atendida", "Atendida"
        NO_ASISTIO = "no_asistio", "No asistió"
        CANCELADA = "cancelada", "Cancelada"
        REPROGRAMADA = "reprogramada", "Reprogramada"

    class Origen(models.TextChoices):
        VENTANILLA = "ventanilla", "Ventanilla"
        AUTOGESTION = "autogestion", "Autogestión (paciente)"
        DERIVACION = "derivacion", "Derivación interna"
        EMERGENCIA = "emergencia", "Emergencia"

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="citas")
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name="citas")
    profesional = models.ForeignKey(
        PerfilProfesional, on_delete=models.PROTECT, related_name="citas"
    )
    fecha_hora = models.DateTimeField(db_index=True)
    duracion_min = models.PositiveSmallIntegerField(default=20)
    estado = models.CharField(max_length=14, choices=Estado.choices, default=Estado.RESERVADA)
    origen = models.CharField(max_length=12, choices=Origen.choices, default=Origen.VENTANILLA)
    motivo = models.CharField(max_length=255, blank=True)
    cita_origen = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reprogramaciones",
        help_text="Si esta cita reemplaza a otra reprogramada.",
    )
    llegada_en = models.DateTimeField(null=True, blank=True)
    atendida_en = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        verbose_name = "cita"
        verbose_name_plural = "citas"
        ordering = ["fecha_hora"]
        indexes = [
            models.Index(fields=["servicio", "fecha_hora"]),
            models.Index(fields=["profesional", "fecha_hora"]),
            models.Index(fields=["expediente", "fecha_hora"]),
        ]
        constraints = [
            # No dos citas activas al mismo profesional a la misma hora
            models.UniqueConstraint(
                fields=["profesional", "fecha_hora"],
                condition=models.Q(estado__in=["reservada", "confirmada",
                                               "en_espera", "en_atencion"]),
                name="uniq_cita_activa_profesional_hora",
            ),
        ]

    def __str__(self):
        return f"Cita {self.servicio} — {self.fecha_hora:%Y-%m-%d %H:%M}"

    @property
    def fin(self):
        return self.fecha_hora + timedelta(minutes=self.duracion_min)
