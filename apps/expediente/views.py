"""
Interfaz web del expediente: búsqueda por cédula y ficha del expediente.

La búsqueda por cédula (informe 7.5) es el punto de entrada de todo el trabajo
clínico: resuelve la persona contra la base institucional, muestra la tarjeta de
verificación con semáforo de matrícula y enlaza al expediente único.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.usuarios import rbac

from .models import Expediente
from .selectors import resumen_expediente
from .services import resolver_por_cedula


@login_required
def buscar(request):
    """Busca una persona por cédula y ofrece abrir su expediente."""
    contexto = {}
    cedula = (request.GET.get("cedula") or "").strip()
    if cedula:
        resultado = resolver_por_cedula(cedula, usuario=request.user)
        if resultado is None:
            messages.warning(
                request,
                f"La cédula {cedula} no está en la base institucional. "
                "Puede registrarla como persona externa.",
            )
        else:
            inst = resultado["institucional"] or {}
            # Semáforo de vinculación (informe 7.5)
            estado = (inst.get("estado") or "").lower()
            if "matricul" in estado:
                semaforo = "success"
            elif inst:
                semaforo = "warning"
            else:
                semaforo = "danger"
            contexto.update({
                "persona": resultado["persona"],
                "expediente": resultado["expediente"],
                "institucional": inst,
                "semaforo": semaforo,
            })
        contexto["cedula"] = cedula
    return render(request, "expediente/buscar.html", contexto)


@login_required
def detalle(request, pk):
    """Ficha del expediente: encabezado, alertas y línea de tiempo (con RBAC)."""
    if not rbac.puede_ver_expediente(request.user):
        messages.error(request, "No tiene permisos para ver expedientes.")
        return redirect("expediente:buscar")

    expediente = get_object_or_404(Expediente, pk=pk)
    break_glass = request.GET.get("break_glass") == "1"
    contexto = resumen_expediente(expediente, request.user, break_glass=break_glass)
    contexto["break_glass"] = break_glass
    return render(request, "expediente/detalle.html", contexto)
