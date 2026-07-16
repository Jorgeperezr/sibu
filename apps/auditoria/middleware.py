"""
Middleware de auditoría: adjunta el usuario e IP de la petición a un contexto
por hilo para que las señales de los modelos registren autoría. El registro
efectivo de cada evento se implementa vía señales por modelo (signals.py).
"""

import threading

_local = threading.local()


def get_auditoria_context():
    return getattr(_local, "context", {})


class AuditoriaMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _local.context = {
            "usuario": getattr(request, "user", None),
            "ip": request.META.get("REMOTE_ADDR"),
            "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
        }
        try:
            return self.get_response(request)
        finally:
            _local.context = {}
