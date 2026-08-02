# ADR-0003: Concurrencia sobre `identificador_externo` resuelta con restricción única + `ON CONFLICT` en BD

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 0 (planeación) — implementación en Bloque 2

> **En pocas palabras:** dos peticiones con el mismo `identificador_externo` que llegan al mismo tiempo no pueden producir un duplicado, porque la restricción `UNIQUE` de PostgreSQL lo hace imposible a nivel de motor. La inserción se hace con `ON CONFLICT DO NOTHING RETURNING *`: si no se devuelve ninguna fila, es porque otra petición ganó la carrera y la respuesta correcta es `409 Conflict`.

## Contexto

El enunciado exige explícitamente dos cosas relacionadas pero distintas: "evitar registros duplicados mediante una restricción única sobre el identificador externo" (un invariante de datos) y "manejar adecuadamente solicitudes concurrentes con el mismo identificador" (ese invariante debe sostenerse incluso bajo carga).

La forma ingenua de resolver esto —hacer un `SELECT` para verificar si ya existe y luego un `INSERT` si no existe— tiene una ventana de tiempo entre la lectura y la escritura que se conoce como **TOCTOU** (*time-of-check to time-of-use*). En esa ventana, otra petición concurrente puede insertar el mismo valor. El resultado es o bien un `IntegrityError` no manejado (un `500` inesperado) o, en el peor caso, un duplicado real si no hay restricción en la base de datos. Es el error más común en pruebas técnicas de este tipo, y exactamente lo que el enunciado pide evitar.

## Decisión

1. La unicidad se garantiza con una restricción `UNIQUE` real en la columna `identificador_externo` a nivel de base de datos. No es solo una validación en la aplicación —eso no sería suficiente bajo concurrencia— sino una garantía que aplica el motor como parte de la misma operación de escritura.
2. La inserción se realiza con una sola sentencia:
   `INSERT ... ON CONFLICT (identificador_externo) DO NOTHING RETURNING *`

   Si la fila retornada es `None`, significa que otra transacción ganó la carrera. El repositorio devuelve `None`; el servicio lo interpreta y lanza `SolicitudDuplicada` → `409 Conflict`.

```python
stmt = (
    insert(Solicitud)
    .values(**datos)
    .on_conflict_do_nothing(index_elements=["identificador_externo"])
    .returning(Solicitud)
)
fila = session.execute(stmt).scalar_one_or_none()
if fila is None:
    raise SolicitudDuplicada(identificador_externo)
```

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `SELECT` para verificar existencia, luego `INSERT` si no existe | Vulnerable a TOCTOU: entre el `SELECT` y el `INSERT` otra transacción puede insertar el mismo valor. Es exactamente el error que el enunciado pide evitar, y el patrón que aparece en la mayoría de implementaciones incorrectas de este requisito. |
| `INSERT` directo capturando el `IntegrityError` en un `try/except` | Funciona (el `UNIQUE` sí lo detecta), pero deja que una excepción de integridad sea el mecanismo de control de flujo normal, lo que dispara un `ROLLBACK` completo de la transacción —más costoso que `ON CONFLICT DO NOTHING`, que resuelve el conflicto sin abortar nada. Es una alternativa razonable de "nivel medio", pero `ON CONFLICT` es más preciso: distingue "conflicto de negocio esperado" (fila `None`) de "error de integridad genuino" (que sí seguiría siendo una excepción real). |
| Bloqueo pesimista (`SELECT ... FOR UPDATE`) antes de insertar | No aplica directamente a un `INSERT` —no hay fila preexistente que bloquear—. Implementarlo requeriría advisory locks por hash del identificador externo, añadiendo complejidad sin ningún beneficio sobre el enfoque atómico que ya ofrece `ON CONFLICT`. |

## Consecuencias

**Lo que se gana:**
- Un solo round-trip a la base de datos por creación, sin transacciones explícitas adicionales ni locks manuales.
- El camino de conflicto es parte del flujo normal de control (`if fila is None`), no una excepción — más fácil de testear de forma determinista.
- Se puede verificar con un test que dispara 20 peticiones concurrentes con el mismo `identificador_externo` y afirma exactamente **1** respuesta `201` y **19** respuestas `409` (está en `tests/test_crear_solicitud.py`).

**Lo que se paga:**
- La sintaxis `ON CONFLICT` es una extensión de PostgreSQL (y SQLite), no SQL estándar. Si se migrara de motor de base de datos, este fragmento puntual necesitaría reescritura. Se acepta porque el enunciado ya fija PostgreSQL como motor — no es una decisión que se tomó sin contexto.
