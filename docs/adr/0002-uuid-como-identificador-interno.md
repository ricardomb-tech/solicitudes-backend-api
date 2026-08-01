# ADR-0002: UUID como identificador interno, distinto del identificador externo

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 0 (planeación) — implementación en Bloque 2

## Contexto

El dominio tiene dos identidades para la misma entidad: el **identificador
externo** (código único asignado por el sistema de origen, dato de negocio) y
la necesidad de una **clave primaria** técnica para la tabla. El enunciado usa
`{id}` en las rutas sugeridas sin aclarar a cuál se refiere. Hay que decidir
qué tipo de dato usar como PK y qué representa `{id}` en la URL.

## Decisión

- La clave primaria de la tabla `solicitudes` es un **UUID v4**, generado por
  la aplicación (o por PostgreSQL vía `gen_random_uuid()`), independiente del
  identificador externo.
- `identificador_externo` es una columna de negocio, con restricción `UNIQUE`,
  pero **no** es la clave primaria.
- `{id}` en las rutas (`GET /solicitudes/{id}`, `PATCH
  /solicitudes/{id}/estado`) se refiere al **UUID interno**. Para buscar por
  el identificador del sistema de origen se usa el filtro
  `GET /solicitudes?identificador_externo=...`.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `SERIAL`/`BIGSERIAL` autoincremental como PK | Expone el volumen de negocio (un competidor o cliente puede estimar cuántas solicitudes existen) y permite enumeración secuencial de recursos (`/solicitudes/1`, `/2`, `/3`...), un antipatrón de seguridad conocido (IDOR por enumeración). |
| Usar `identificador_externo` como clave primaria y como `{id}` de ruta | Acopla el modelo de datos interno a un identificador cuyo formato y unicidad dependen de un sistema externo que no controlamos; si ese sistema cambia su esquema de codificación, se rompe la PK de nuestra tabla. Además, mezclar "la ruta REST" con "el identificador de negocio" hace ambiguo qué pasa si dos solicitudes de sistemas de origen distintos coinciden en el mismo código (edge case no descartable sin esta separación). |

## Consecuencias

**A favor:**
- El UUID es generable sin round-trip a la base de datos (útil para
  correlación de logs antes incluso de persistir) y no colisiona si en el
  futuro se federan varias instancias del servicio.
- La relación 1 a 1 entre UUID interno e identificador externo, ambos únicos,
  permite optimizar la búsqueda por cualquiera de los dos sin ambigüedad.

**Costo asumido:**
- Un UUID (16 bytes, o 36 caracteres en texto) pesa más que un entero de 4-8
  bytes como índice, y tiene peor localidad de escritura en el árbol B del
  índice que un entero secuencial (los inserts no son "al final" del índice).
  A la escala de esta prueba (y de la mayoría de sistemas de gestión de
  solicitudes institucionales) ese costo es irrelevante frente al beneficio de
  seguridad y desacoplamiento.
