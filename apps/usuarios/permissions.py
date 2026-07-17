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


class PuedeVerAtencion(BasePermission):
    """
    Aplica `rbac.puede_ver_atencion` al objeto de la petición.

    Defensa a nivel de objeto: complementa el filtrado de queryset. La API es
    una superficie nueva para el sello de Psicología, así que el control no
    puede depender solo de que el queryset esté bien filtrado.

    Acepta tanto una Atencion como cualquier objeto que tenga `.atencion`
    (FichaPsicologica, AtencionOdontologia, etc.).
    """

    def has_object_permission(self, request, view, obj):
        from apps.expediente.models import Atencion

        from . import rbac

        atencion = obj if isinstance(obj, Atencion) else getattr(obj, "atencion", None)
        if atencion is None:
            return True
        return rbac.puede_ver_atencion(request.user, atencion)


class EsDelServicio(BasePermission):
    """
    Permite el acceso solo a los profesionales de un servicio concreto.

    Se usa para endpoints que no cuelgan de una Atencion (por ejemplo la
    bandeja de derivaciones de un servicio).
    """

    codigo_servicio: str = ""

    def has_permission(self, request, view):
        from .rbac import servicios_del_usuario

        codigo = getattr(view, "codigo_servicio", self.codigo_servicio)
        if not codigo:
            return True
        from apps.core.models import Servicio

        servicio = Servicio.objects.filter(codigo=codigo).first()
        if servicio is None:
            return False
        return servicio.pk in servicios_del_usuario(request.user)
