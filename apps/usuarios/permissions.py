"""Permisos DRF reutilizables para el RBAC de SIBU."""

from rest_framework.permissions import BasePermission

from .models import Rol


class EsProfesionalDelServicio(BasePermission):
    """Permite el acceso solo si el usuario tiene asignado el servicio del objeto."""

    def has_object_permission(self, request, view, obj):
        servicio = getattr(obj, "servicio_id", None)
        if servicio is None:
            return True
        perfil = getattr(request.user, "perfil", None)
        if perfil is None:
            return False
        return perfil.servicios.filter(pk=servicio).exists()


class EsAdministrador(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.rol_principal == Rol.ADMIN_GENERAL
