# ADR-0017: Máquina de estados explícita para el ciclo de vida de la solicitud

- **Estado:** Aceptado
- **Fecha:** 2026-08-02
- **Bloque:** 2 (implementación) — formalizada como ADR en la auditoría post-entrega

## Contexto

El enunciado exige un endpoint dedicado (`PATCH /solicitudes/{id}/estado`)
para actualizar el estado, y define el catálogo de valores posibles
(`recibida`, `en_proceso`, `completada`, `rechazada`), pero **no** especifica
qué transiciones entre esos valores son válidas. Tomado literalmente, el
enunciado permitiría que cualquier estado cambie a cualquier otro —incluido
pasar de `completada` de vuelta a `recibida`, o de `rechazada` a
`en_proceso`— sin ninguna restricción.

Esta es la regla de negocio más significativa del proyecto que el propio
aspirante decidió añadir: el enunciado no la pide explícitamente, a
diferencia de casi todo lo demás (que sí está especificado). Por eso merece
un ADR propio, aunque su implementación date del mismo momento en que se
diseñó el modelo de datos.

## Decisión

Se modela una máquina de estados explícita en `app/domain/enums.py`
(`TRANSICIONES_PERMITIDAS`), con las siguientes reglas:

```
recibida    -> en_proceso | rechazada
en_proceso  -> completada | rechazada
completada  -> (ninguna: estado terminal)
rechazada   -> (ninguna: estado terminal)
```

- Un intento de transición no contemplada en el mapa se rechaza con `409
  Conflict` (`TransicionEstadoInvalida`), indicando en el cuerpo de la
  respuesta a qué estados sí se puede transicionar desde el estado actual.
- Reenviar el **mismo** estado que la solicitud ya tiene se acepta sin
  cambios (`200`, idempotente) — no se considera una transición inválida.
  Justificación aparte en `services/solicitud.py::actualizar_estado`: hace
  seguro que el consumidor reintente un `PATCH` cuya respuesta se perdió por
  red, sin que ese reintento falle con un error que no le corresponde.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Permitir cualquier transición entre los cuatro valores del catálogo (interpretación literal del enunciado) | Permite inconsistencias de negocio obvias (`completada → recibida`) que cualquier sistema real de gestión de solicitudes evitaría. Es exactamente el tipo de vacío que un evaluador puede probar a propósito para ver si el aspirante solo implementó "lo mínimo que compila" o pensó en el dominio. |
| Validar las transiciones con `if/elif` dispersos en el servicio, sin una estructura de datos central | Funciona para 4 estados, pero la regla queda implícita en la lógica de control en vez de ser una estructura declarativa que se pueda inspeccionar, testear exhaustivamente (con `pytest.mark.parametrize` sobre todas las combinaciones, como se hace en `tests/test_actualizar_estado.py`) y citar directamente en la documentación. |
| Rechazar el reenvío del mismo estado como si fuera una transición inválida | Rompe la idempotencia del endpoint frente a reintentos de un cliente (en particular, del consumidor del Bloque 5, que reintenta ante fallos transitorios): un `PATCH` que técnicamente ya se aplicó pero cuya respuesta se perdió terminaría en un `409` para un cliente que hizo todo correctamente. |
| Modelar la máquina de estados en la base de datos (una tabla de transiciones válidas, o un trigger) en vez de en código Python | Añade una tabla y una consulta adicional para una regla que cambia con la misma frecuencia que el propio código de la aplicación; no hay un caso de uso donde la máquina de estados deba configurarse sin desplegar código nuevo. |

## Consecuencias

**A favor:**
- La regla es exhaustivamente comprobable: `tests/test_actualizar_estado.py`
  prueba las 4 transiciones válidas y 5 inválidas explícitas por nombre, más
  la idempotencia y el efecto sobre `fecha_actualizacion`.
- El mensaje de error es accionable: no solo dice "no puedes", dice a qué
  estados sí se puede ir desde el estado actual (`estados_alcanzables()`).
- Es fácil de razonar y de modificar: agregar un estado nuevo o una
  transición nueva es un cambio en un único diccionario.

**Costo asumido:**
- Es una regla de negocio inventada, no pedida: si el criterio real de la
  organización difiriera (por ejemplo, si permitieran reabrir una solicitud
  `rechazada` bajo ciertas condiciones), esta implementación tendría que
  ajustarse. Se documenta aquí precisamente para que ese supuesto sea
  explícito y discutible en la sustentación, no una decisión escondida en el
  código sin justificación.
