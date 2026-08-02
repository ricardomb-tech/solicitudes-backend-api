# ADR-0002: UUID como identificador interno, distinto del identificador externo

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 0 (planeación) — implementación en Bloque 2

> **En pocas palabras:** la tabla tiene dos identidades para la misma entidad: un UUID interno que el sistema genera (la clave primaria técnica) y el `identificador_externo` que envía el cliente (la clave de negocio). Separarlos evita que la base de datos interna quede acoplada al esquema de numeración de un sistema que no controlamos.

## Contexto

El dominio tiene dos identidades para la misma entidad: el **identificador externo** (código único asignado por el sistema de origen, dato de negocio) y la necesidad de una **clave primaria** técnica para la tabla. El enunciado usa `{id}` en las rutas sugeridas sin aclarar a cuál se refiere. Hay que decidir qué tipo de dato usar como PK y qué representa `{id}` en la URL.

## Decisión

- La clave primaria de la tabla `solicitudes` es un **UUID v4**, generado por PostgreSQL vía `gen_random_uuid()`, completamente independiente del identificador externo.
- `identificador_externo` es una columna de negocio con restricción `UNIQUE`, pero **no** es la clave primaria.
- `{id}` en las rutas (`GET /solicitudes/{id}`, `PATCH /solicitudes/{id}/estado`) se refiere al **UUID interno**. Para buscar por el código del sistema de origen se usa el filtro `GET /solicitudes?identificador_externo=...`.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `SERIAL`/`BIGSERIAL` autoincremental como PK | Expone el volumen de negocio: un competidor puede hacer `GET /solicitudes/1`, `/2`, `/3`... y estimar cuántas solicitudes existen. Además permite iterar sobre todos los registros sin ningún permiso — el patrón IDOR por enumeración, un antipatrón de seguridad conocido. |
| Usar `identificador_externo` como clave primaria y como `{id}` de ruta | Acopla el modelo de datos interno a un código cuyo formato y unicidad dependen de un sistema que no controlamos. Si ese sistema cambia su esquema de numeración, hay que migrar la PK de la tabla — una operación costosa y riesgosa. Además, si en el futuro dos sistemas de origen distintos usaran el mismo código (un edge case no descartable), no habría forma de distinguirlos. |

## Consecuencias

**Lo que se gana:**
- El UUID se puede generar antes incluso de persistir la solicitud (útil para asociar el `correlation_id` al registro desde el inicio del request).
- La relación 1 a 1 entre UUID interno e identificador externo, ambos únicos, permite optimizar la búsqueda por cualquiera de los dos sin ambigüedad.
- El enunciado y las rutas REST quedan desacoplados de detalles internos del sistema de origen.

**Lo que se paga:**
- Un UUID ocupa 16 bytes (o 36 caracteres en texto) frente a los 4-8 bytes de un entero, y tiene peor localidad de escritura en el árbol B del índice porque los inserts no son "al final" como sí lo son con un autoincremental. A la escala de un sistema de gestión de solicitudes institucionales, ese costo de almacenamiento e índice es irrelevante frente al beneficio de seguridad y desacoplamiento.
