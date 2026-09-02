"""
Interfaz web del expediente: búsqueda por cédula y ficha del expediente.

La búsqueda por cédula (informe 7.5) es el punto de entrada de todo el trabajo
clínico: resuelve la persona contra la base institucional, muestra la tarjeta de
verificación con semáforo de matrícula y enlaza al expediente único.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.navegacion import acciones_expediente
from apps.usuarios import rbac

from .models import Expediente, Persona
from .selectors import resumen_expediente
from .services import registrar_persona, resolver_por_cedula

# Campos que acepta el alta. Explícito para no volcar el POST entero en el
# modelo: un campo de más aquí es un dato que nadie validó.
CAMPOS_ALTA = (
    "cedula",
    "tipo_documento",
    "nombres",
    "apellidos",
    "fecha_nacimiento",
    "sexo",
    "tipo_vinculo",
    "correo_institucional",
    "correo_personal",
    "telefono",
    "celular",
)


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
            contexto.update(
                {
                    "persona": resultado["persona"],
                    "expediente": resultado["expediente"],
                    "institucional": inst,
                    "semaforo": semaforo,
                }
            )
        contexto["cedula"] = cedula
    return render(request, "expediente/buscar.html", contexto)


@login_required
def nuevo(request):
    """
    Alta de una persona y apertura de su expediente.

    La búsqueda ofrecía "puede registrarla como persona externa" sin dar por
    dónde: sin esta pantalla, dar de alta a un paciente exigía el shell, y todos
    los módulos parten de un expediente existente.
    """
    if not rbac.puede_ver_expediente(request.user):
        messages.error(request, "No tiene permisos para registrar expedientes.")
        return redirect("expediente:buscar")

    datos = {"cedula": (request.GET.get("cedula") or "").strip()}

    if request.method == "POST":
        datos = {campo: (request.POST.get(campo) or "").strip() for campo in CAMPOS_ALTA}
        try:
            expediente = registrar_persona(datos, usuario=request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                f"Expediente {expediente.numero_expediente} abierto para "
                f"{expediente.persona.nombre_completo}.",
            )
            return redirect("expediente:detalle", pk=expediente.pk)

    return render(
        request,
        "expediente/nuevo.html",
        {
            "datos": datos,
            "vinculos": Persona.TipoVinculo.choices,
        },
    )


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
    # Sin esto el expediente era una pantalla de solo lectura: la ficha se veía,
    # pero abrir una consulta exigía teclear la URL a mano.
    contexto["acciones"] = acciones_expediente(request.user)
    return render(request, "expediente/detalle.html", contexto)
