"""
Expediente único de la persona y modelo base de atención.

Toda ficha de servicio (Medicina, Enfermería, …) extiende `Atencion` mediante
una relación OneToOne (patrón "clase base + extensión", informe 4.2 y 11.3).
"""
from django.db import models

from apps.core.models import ModeloBase, Servicio
from apps.usuarios.models import PerfilProfesional


class Persona(ModeloBase):
    """Datos demográficos consolidados. Clave de vinculación: cédula."""

    class TipoVinculo(models.TextChoices):
        ESTUDIANTE = "estudiante", "Estudiante"
        DOCENTE = "docente", "Docente"
        ADMINISTRATIVO = "administrativo", "Administrativo"
        TRABAJADOR = "trabajador", "Trabajador"
        EXTERNO = "externo", "Externo/Particular"

    cedula = models.CharField(max_length=13, unique=True, db_index=True)
    tipo_documento = models.CharField(max_length=20, default="cedula")
    nombres = models.CharField(max_length=120)
    apellidos = models.CharField(max_length=120)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=20, blank=True)
    genero = models.CharField(max_length=30, blank=True)
    tipo_vinculo = models.CharField(max_length=20, choices=TipoVinculo.choices)
    correo_institucional = models.EmailField(blank=True)
    correo_personal = models.EmailField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    celular = models.CharField(max_length=20, blank=True)

    # Estructuras semi-variables (informe 7.3)
    procedencia = models.JSONField(default=dict, blank=True)
    residencia_actual = models.JSONField(default=dict, blank=True)
    contacto_referencia = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "persona"
        verbose_name_plural = "personas"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.apellidos} {self.nombres} ({self.cedula})"

    @property
    def nombre_completo(self):
        return f"{self.apellidos} {self.nombres}".strip()


class Expediente(ModeloBase):
    """Carpeta digital única que consolida todas las atenciones de la persona."""

    persona = models.OneToOneField(Persona, on_delete=models.PROTECT, related_name="expediente")
    numero_expediente = models.CharField(max_length=20, unique=True, db_index=True)
    grupo_sanguineo = models.CharField(max_length=5, blank=True)
    discapacidad_tipo = models.CharField(max_length=60, blank=True)
    discapacidad_porcentaje = models.PositiveSmallIntegerField(null=True, blank=True)
    fecha_apertura = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "expediente"
        verbose_name_plural = "expedientes"

    def __str__(self):
        return f"Expediente {self.numero_expediente}"


class AlertaClinica(ModeloBase):
    """Banderas visibles en todo el expediente (alergias, riesgo, alertas sociales)."""

    class Tipo(models.TextChoices):
        ALERGIA = "alergia", "Alergia"
        RIESGO = "riesgo", "Riesgo clínico"
        SOCIAL = "social", "Alerta social"
        NEE = "nee", "Necesidad educativa especial"

    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="alertas")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    descripcion = models.CharField(max_length=255)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "alerta clínica"
        verbose_name_plural = "alertas clínicas"

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.descripcion}"


class Consentimiento(ModeloBase):
    """Consentimiento informado digitalizado (informe 14.3)."""

    expediente = models.ForeignKey(
        Expediente, on_delete=models.CASCADE, related_name="consentimientos"
    )
    tipo = models.CharField(max_length=80)
    texto_version = models.CharField(max_length=20)
    otorgado = models.BooleanField(default=False)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "consentimiento"
        verbose_name_plural = "consentimientos"


class Atencion(ModeloBase):
    """
    Base común de toda atención. Las apps de servicio la extienden 1:1.
    Una atención firmada es inmutable; las correcciones se hacen por enmienda.
    """

    class Tipo(models.TextChoices):
        PRIMERA = "primera", "Primera"
        SUBSECUENTE = "subsecuente", "Subsecuente"

    class Origen(models.TextChoices):
        CITA = "cita", "Cita"
        ESPONTANEA = "espontanea", "Demanda espontánea"
        DERIVACION = "derivacion", "Derivación"
        EMERGENCIA = "emergencia", "Emergencia"

    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        CERRADA = "cerrada", "Cerrada"
        FIRMADA = "firmada", "Firmada"
        ENMENDADA = "enmendada", "Enmendada"

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="atenciones")
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name="atenciones")
    profesional = models.ForeignKey(
        PerfilProfesional, on_delete=models.PROTECT, related_name="atenciones"
    )
    fecha_hora = models.DateTimeField(db_index=True)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.PRIMERA)
    origen = models.CharField(max_length=12, choices=Origen.choices, default=Origen.CITA)
    motivo_consulta = models.TextField(blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)

    # Instantánea de los datos institucionales al momento de la atención (7.5)
    snapshot_academico = models.JSONField(default=dict, blank=True)

    firmada_en = models.DateTimeField(null=True, blank=True)
    hash_firma = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "atención"
        verbose_name_plural = "atenciones"
        ordering = ["-fecha_hora"]
        indexes = [
            models.Index(fields=["expediente", "fecha_hora"]),
            models.Index(fields=["servicio", "fecha_hora"]),
        ]

    def __str__(self):
        return f"Atención {self.servicio} — {self.expediente} ({self.fecha_hora:%Y-%m-%d})"

    @property
    def inmutable(self):
        return self.estado in {self.Estado.FIRMADA, self.Estado.ENMENDADA}
