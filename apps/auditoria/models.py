"""
Bitácora inmutable (append-only). Registra CRUD, lecturas de historia clínica,
exportaciones, break-the-glass y eventos del sistema (informe 5.2 M19, 14.5).
El rol de aplicación no tiene permiso UPDATE/DELETE sobre esta tabla en la BD.
"""
from django.db import models

from apps.usuarios.models import Usuario


class LogAuditoria(models.Model):
    class Accion(models.TextChoices):
        CREATE = "create", "Crear"
        READ = "read", "Leer"
        UPDATE = "update", "Actualizar"
        SOFT_DELETE = "soft_delete", "Eliminar (lógico)"
        LOGIN = "login", "Inicio de sesión"
        LOGOUT = "logout", "Cierre de sesión"
        EXPORT = "export", "Exportar"
        PRINT = "print", "Imprimir"
        BREAK_GLASS = "break_glass", "Acceso de emergencia"

    fecha_hora = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(Usuario, null=True, blank=True, on_delete=models.SET_NULL)
    rol_activo = models.CharField(max_length=20, blank=True)
    accion = models.CharField(max_length=14, choices=Accion.choices)
    modulo = models.CharField(max_length=40, blank=True)
    entidad = models.CharField(max_length=60, blank=True)
    entidad_id = models.CharField(max_length=40, blank=True)
    expediente_id = models.PositiveBigIntegerField(null=True, blank=True)
    detalle = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    resultado = models.CharField(max_length=20, default="ok")

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-fecha_hora"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Los registros de auditoría son inmutables.")
        super().save(*args, **kwargs)
