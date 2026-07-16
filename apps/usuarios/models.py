"""
Usuario del sistema y perfil profesional.

El RBAC (informe, sección 10) se apoya en los grupos nativos de Django más
permisos por objeto (guardian) filtrados por `servicio`. Los roles canónicos
se definen como grupos cargados por fixture; aquí solo se modela la cuenta y
su relación con servicios y sección.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import Seccion, Servicio


class Rol(models.TextChoices):
    ADMIN_GENERAL = "admin_general", "Administrador General"
    DIRECTOR = "director", "Director de la Unidad"
    COORDINADOR = "coordinador", "Coordinador de Sección"
    PROFESIONAL = "profesional", "Profesional de Servicio"
    LABORATORIO = "laboratorio", "Personal de Laboratorio"
    FARMACIA = "farmacia", "Personal de Farmacia"
    ADMINISTRATIVO = "administrativo", "Personal Administrativo"
    CONSULTA = "consulta", "Consulta Restringida"
    USUARIO_FINAL = "usuario_final", "Usuario Final (paciente/beneficiario)"


class Usuario(AbstractUser):
    """Cuenta de acceso. `username` = cédula o usuario institucional."""

    cedula = models.CharField(max_length=13, unique=True, null=True, blank=True)
    rol_principal = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CONSULTA)
    mfa_habilitado = models.BooleanField(default=False)
    telefono = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_full_name() or self.username


class PerfilProfesional(models.Model):
    """Datos del profesional que atiende: servicios, registro y firma."""

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="perfil")
    seccion = models.ForeignKey(Seccion, null=True, blank=True, on_delete=models.SET_NULL)
    servicios = models.ManyToManyField(Servicio, related_name="profesionales", blank=True)
    titulo = models.CharField(max_length=120, blank=True)
    registro_profesional = models.CharField(
        max_length=60, blank=True, help_text="Registro (ACESS/SENESCYT) del profesional."
    )
    puede_firmar_digital = models.BooleanField(default=False)

    class Meta:
        verbose_name = "perfil profesional"
        verbose_name_plural = "perfiles profesionales"

    def __str__(self):
        return f"Perfil de {self.usuario}"
