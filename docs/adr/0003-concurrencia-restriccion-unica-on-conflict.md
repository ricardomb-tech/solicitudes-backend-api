# ADR-0003: Concurrencia sobre `identificador_externo` resuelta con restricción única + `ON CONFLICT` en BD

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 0 (planeación) — implementación en Bloque 2

## Contexto

El enunciado exige explícitamente: "evitar registros duplicados mediante una
restricción única sobre el identificador externo" y, por separado, "manejar
adecuadamente solicitudes concurrentes con el mismo identificador". Son dos
requisitos relacionados pero distintos: el primero pide un invariante de
datos; el segundo pide que ese invariante se sostenga incluso cuando dos
peticiones llegan casi al mismo tiempo con el mismo valor.

La forma ingenua de "verificar duplicados" —consultar si existe y luego
insertar si no— tiene una ventana de tiempo entre la lectura y la escritura
(TOCTOU: *time-of-check to time-of-use*) en la que otra transacción concurrente
puede insertar el mismo valor. Bajo carga real, esto produce o bien un
`IntegrityError` no manejado (500) o, peor, un duplicado real si no hay
restricción a nivel de base de datos.

## Decisión

1. La unicidad se garantiza con una restricción `UNIQUE` real en la columna
   `identificador_externo` a nivel de base de datos (no solo una validación en
   la aplicación) — este es el único mecanismo verdaderamente atómico frente a
   concurrencia, porque lo aplica el motor de la base de datos como parte de
   la misma operación de escritura.
2. La inserción se realiza con
   `INSERT ... ON CONFLICT (identificador_externo) DO NOTHING RETURNING *`
   en una sola sentencia. Si la fila retornada es `None`, significa que otra
   transacción ganó la carrera y se responde `409 Conflict`.

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
| `SELECT` para verificar existencia, luego `INSERT` si no existe | Vulnerable a TOCTOU: entre el `SELECT` y el `INSERT` otra transacción puede insertar el mismo valor. Es el error más común en pruebas de este tipo y exactamente lo que el enunciado pide evitar. |
| `INSERT` directo, capturando `IntegrityError` en un `try/except` | Funciona (el `UNIQUE` de la BD sí lo detecta), pero dejar que la excepción de integridad sea el mecanismo de control de flujo normal dispara un `ROLLBACK` completo de la transacción en curso (más costoso y menos explícito que `ON CONFLICT DO NOTHING`, que resuelve el conflicto sin abortar la transacción). Se considera una alternativa razonable de "nivel medio", pero `ON CONFLICT` es más preciso semánticamente: distingue "conflicto de negocio esperado" (se maneja con una fila `None`) de "error de integridad inesperado" (que sí seguiría siendo una excepción real). |
| Bloqueo pesimista (`SELECT ... FOR UPDATE`) antes de insertar | No aplica directamente a un `INSERT` (no hay fila que bloquear todavía); sería necesario un patrón distinto (p. ej. un advisory lock por hash del identificador externo), que añade complejidad sin beneficio sobre el enfoque atómico de `ON CONFLICT`. |

## Consecuencias

**A favor:**
- Un solo *round-trip* a la base de datos por creación, sin necesidad de
  transacciones explícitas adicionales ni bloqueos manuales.
- El camino de conflicto es parte del flujo normal de control (`if fila is
  None`), no una excepción — más fácil de testear de forma determinista con
  peticiones concurrentes reales.
- Se puede probar con un test que dispara *N* peticiones concurrentes con el
  mismo `identificador_externo` y afirma exactamente **1** respuesta `201` y
  *N−1* respuestas `409`.

**Costo asumido:**
- Acopla el código de inserción a la sintaxis específica de PostgreSQL
  (`ON CONFLICT` es una extensión de PostgreSQL/SQLite, no SQL estándar). Se
  acepta porque el enunciado ya fija PostgreSQL como motor; si se migrara de
  motor, este fragmento puntual necesitaría reescritura (el resto de la capa
  de repositorio, escrita en SQLAlchemy Core/ORM genérico, no).
