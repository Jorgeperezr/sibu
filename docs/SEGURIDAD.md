# Control de acceso: cómo está montado y cómo no romperlo

Este documento describe lo que el código hace hoy, no lo que debería hacer. Si
algo aquí no coincide con `apps/usuarios/rbac.py`, manda el código y este
archivo está desactualizado.

## La regla que no se negocia

**El contenido clínico de Psicología no es accesible fuera del servicio.** Ni
para Dirección, ni para Coordinación, ni para administración, ni con acceso de
emergencia. `rbac.puede_ver_atencion` lo aplica sin excepciones:

```python
if servicio.codigo in SERVICIOS_CONFIDENCIALES:
    return user.rol_principal == Rol.PROFESIONAL and servicio.pk in servicios_del_usuario(user)
```

Tres consecuencias que cuestan caro olvidar:

1. **La existencia de un dato también identifica.** Que alguien tenga cita con
   Psicología dice que es paciente de Psicología. Por eso el calendario da
   conteos y no nombres, la trazabilidad oculta la fila entera —no solo el
   motivo— a quien no es de ninguno de los dos servicios implicados, y el
   tablero de Dirección suprime los conteos menores que `K_MINIMO`.
2. **El tratante entra antes que la regla.** `puede_ver_atencion` concede
   acceso a quien realizó la atención *antes* de mirar si el servicio es
   confidencial. Eso es correcto —un profesional ve lo suyo— y convierte
   «nombrarse tratante» en una vía de entrada: por eso
   `verificar_profesional_del_servicio` impide abrir una atención en un
   servicio ajeno.
3. **Una marca no es una protección.** La trazabilidad devolvía un campo
   `confidencial: True` y a continuación imprimía el motivo. Marcar sirve para
   pintar un candado; separar el dato de quien no debe verlo es otra cosa.

## Las cuatro capas

Ninguna basta sola. Un fallo en una no debería filtrar nada.

| Capa | Dónde | Qué hace |
|---|---|---|
| **Permiso de vista** | `permission_classes`, `_solo_personal()` | Rechaza antes de tocar datos. Es la única que protege el `create`: un POST no pasa por el queryset. |
| **Filtrado de queryset** | `get_queryset()` | Lo que no está en el queryset devuelve 404 aunque se adivine el id. Protege lista y detalle. |
| **Permiso de objeto** | `PuedeVerAtencion` | Aplica `puede_ver_atencion` a la fila concreta. Solo corre si la vista llama a `get_object()`. |
| **Regla de dominio** | `services.py` | Vive donde pasan la pantalla, la API y lo que se escriba mañana. |

**La capa de servicios es la que importa.** Las dos veces que un agujero
sobrevivió a una corrección fue porque la regla estaba en la vista y no en el
servicio: la pantalla de Psicología comprobaba el servicio con
`verificar_es_del_servicio` y el endpoint equivalente no comprobaba nada.

## Funciones y qué significa cada una

- **`puede_ver_expediente(user)`** — ¿es personal de la Unidad? Roles
  PROFESIONAL, COORDINADOR, DIRECTOR, ADMINISTRATIVO, LABORATORIO, FARMACIA, o
  administrador. Deja fuera a `USUARIO_FINAL`, que es la cuenta de un
  estudiante y trabaja por el portal.
- **`puede_ver_atencion(user, atencion)`** — la regla fina, con el sello.
- **`atenciones_visibles(user, queryset)`** — la anterior a nivel de consulta.
  **Devuelve cero para los roles FARMACIA y LABORATORIO**, por separación de
  funciones clínica. Usarla para filtrar recetas u órdenes deja al farmacéutico
  sin mostrador; para eso está la siguiente.
- **`visible_para_personal(user, queryset, campo_servicio=None)`** — el suelo
  común: hay que ser personal, y lo confidencial solo lo ve su servicio. No
  estrecha más. Un endpoint que necesite una regla más estrecha la aplica
  encima.
- **`verificar_profesional_del_servicio(perfil, servicio)`** — una atención se
  abre en el servicio propio.
- **`EsPersonalDeLaUnidad`** — el par de escritura de `visible_para_personal`.

## Al añadir un endpoint o una pantalla

**Endpoint (DRF):**

```python
class LoQueSeaViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, EsPersonalDeLaUnidad]

    def get_queryset(self):
        return visible_para_personal(
            self.request.user, super().get_queryset(), campo_servicio="atencion__servicio"
        )
```

`campo_servicio` solo si el modelo llega a un `Servicio`; si no, se omite.
Si el objeto cuelga de una `Atencion`, añada `PuedeVerAtencion` y llame a
`get_object()` dentro de cada `@action(detail=True)` —un action que consulta
por `pk` a mano se salta el permiso de objeto—.

**Pantalla web:** `@login_required` **no basta**. Solo pregunta si hay sesión,
nunca de quién. Añada la comprobación que corresponda:
`rbac.puede_ver_expediente`, `verificar_acceso_atencion` o
`verificar_es_del_servicio`.

## Los dos barridos

No hay que acordarse de nada: dos pruebas recorren el sistema entero y una
puerta nueva entra sola.

- **`apps/core/tests/test_api_superficie.py`** recorre el router de la API. Un
  estudiante no puede leer filas (403 o lista vacía) ni escribir (403 o 405,
  **nunca 400** — un 400 es la validación diciendo que la autorización dejó
  pasar).
- **`apps/core/tests/test_web_superficie.py`** recorre el resolver de URLs. Lo
  que un estudiante SÍ puede abrir está en una lista con su razón: añadir algo
  ahí obliga a justificarlo a mano.

Ambos **siembran el sistema entero antes de mirar**. Sin datos todas las listas
salen vacías y la prueba pasaría afirmando nada, que es peor que no tenerla.

## Lo que ya pasó

Por si sirve de aviso sobre por dónde vuelven estas cosas:

| Qué | Cómo |
|---|---|
| `resolver_por_cedula` | Tres puertas: la vista `buscar`, la API y el JSON del formulario de reserva. No solo revela: **crea** la persona y su expediente. |
| Listas sin filtrar | `ExpedienteViewSet.retrieve` comprobaba; `list` no. |
| Escrituras | Doce endpoints donde la autorización no llegaba a correr. Un estudiante se concedía una beca y creaba la agenda de un profesional. |
| Escalada por tratante | Un médico abría un proceso psicológico y quedaba de tratante. |
| Regla escrita sin implementar | `# placeholder: la validación de servicio-profesional es de RBAC`, seguido de `pass`. |
