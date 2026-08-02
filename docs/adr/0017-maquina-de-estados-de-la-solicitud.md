# ADR-0017: Máquina de estados explícita para el ciclo de vida de la solicitud

- **Estado:** Aceptado
- **Fecha:** 2026-08-02
- **Bloque:** 2 (implementación) — formalizada como ADR en la auditoría post-entrega

> **En pocas palabras:** el enunciado no prohíbe pasar de `completada` de vuelta a `recibida`, pero cualquier sistema real de gestión de solicitudes lo haría. Se implementó una máquina de estados explícita que hace esa regla verificable por un test y defenible en la sustentación, en lugar de dejarla como una convención implícita que nadie garantiza.

## Contexto

El enunciado define el endpoint `PATCH /solicitudes/{id}/estado` y los cuatro valores posibles (`recibida`, `en_proceso`, `completada`, `rechazada`), pero **no especifica qué transiciones son válidas**. Tomado al pie de la letra, permitiría pasar de `completada` de vuelta a `recibida`, o de `rechazada` a `en_proceso`, sin ninguna restricción.

Esta es la regla de negocio más significativa que se agregó sin que el enunciado la pidiera explícitamente — a diferencia de casi todo lo demás, que sí está especificado. Por eso merece un ADR propio, para que la decisión sea visible y defendible.

## Decisión

Se modela una máquina de estados explícita en `app/domain/enums.py` (`TRANSICIONES_PERMITIDAS`):

```
recibida    →  en_proceso | rechazada
en_proceso  →  completada | rechazada
completada  →  (ninguna — estado terminal)
rechazada   →  (ninguna — estado terminal)
```

- Una transición no contemplada en el mapa devuelve `409 Conflict` (`TransicionEstadoInvalida`), indicando en el cuerpo de la respuesta a qué estados sí se puede ir desde el estado actual.
- Reenviar el **mismo** estado que la solicitud ya tiene se acepta sin cambios (`200`, idempotente). Justificación: hace seguro que el consumidor reintente un `PATCH` cuya respuesta se perdió por red, sin que ese reintento falle con un `409` que no le corresponde.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Permitir cualquier transición entre los cuatro valores (interpretación literal del enunciado) | Permite inconsistencias de negocio obvias (`completada → recibida`) que cualquier sistema real evitaría. Un evaluador puede probar esto a propósito para ver si la implementación es solo "lo mínimo que compila" o si consideró el dominio. |
| Validar transiciones con `if/elif` dispersos en el servicio, sin estructura de datos central | Funciona para 4 estados. Pero la regla queda implícita en la lógica de control, no como una estructura declarativa que se pueda inspeccionar, probar con `pytest.mark.parametrize` sobre todas las combinaciones posibles y citar directamente en la documentación. |
| Rechazar el reenvío del mismo estado como si fuera una transición inválida | Rompe la idempotencia frente a reintentos del consumidor (ADR-0013): un `PATCH` que técnicamente ya se aplicó pero cuya respuesta se perdió terminaría en `409` para un cliente que hizo todo correctamente. |
| Modelar la máquina de estados en la base de datos (tabla de transiciones válidas, o un trigger) | Añade una tabla y una consulta adicional para una regla que cambia con la misma frecuencia que el código de la aplicación. No hay ningún caso de uso donde la máquina de estados deba configurarse sin desplegar código nuevo. |

## Consecuencias

**Lo que se gana:**
- La regla es exhaustivamente testeable: `tests/test_actualizar_estado.py` prueba las 4 transiciones válidas y 5 inválidas explícitas por nombre, más la idempotencia y el efecto sobre `fecha_actualizacion`.
- El mensaje de error es accionable: no solo dice "no puedes", dice a qué estados sí se puede ir desde el estado actual (`estados_alcanzables()`).
- Agregar un estado nuevo o una transición nueva es un cambio en un único diccionario en `domain/enums.py`.

**Lo que se paga:**
- Es una regla de negocio inventada, no pedida: si el criterio real de la organización difiriera (por ejemplo, si permitieran reabrir una solicitud `rechazada` bajo ciertas condiciones), esta implementación habría que ajustarla. Se documenta aquí precisamente para que ese supuesto sea explícito y discutible en la sustentación, no una decisión escondida en el código sin justificación.
