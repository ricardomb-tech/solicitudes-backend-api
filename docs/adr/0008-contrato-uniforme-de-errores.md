# ADR-0008: Contrato uniforme de errores y no exposición de detalles técnicos

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 3

## Contexto

El enunciado exige dos cosas relacionadas: "utilizar códigos HTTP coherentes" y
"evitar la exposición de información técnica sensible en los errores". Además
pide "manejo centralizado de excepciones".

Sin una decisión explícita, una API típica termina con tres formatos de error
distintos: el de las validaciones de Pydantic, el de las `HTTPException`
lanzadas a mano, y el de los fallos no controlados. Un cliente necesitaría
entonces tres rutinas de manejo de errores.

## Decisión

**1. Un único contrato de error**, inspirado en RFC 9457 (*Problem Details for
HTTP APIs*), aplicado a **todos** los errores de la API incluidos los 404 de
rutas inexistentes:

```json
{
  "tipo": "solicitud_duplicada",
  "titulo": "Ya existe una solicitud registrada con ese identificador externo.",
  "estado": 409,
  "correlation_id": "32eedbd6-e44b-4673-9e79-25b67a021a67",
  "detalles": [ { "campo": "identificador_externo", "...": "..." } ]
}
```

`tipo` es el identificador estable por el que el cliente debe ramificar su
lógica. `titulo` es texto para humanos y puede cambiar sin romper integraciones.

**2. Traducción centralizada de excepción de dominio a código HTTP** en un
único diccionario (`MAPA_HTTP` en `app/core/error_handlers.py`). Las
excepciones de dominio no heredan de `HTTPException` ni conocen códigos HTTP.

**3. Asimetría deliberada entre log y respuesta** para los errores no
controlados:
- Al log: tipo de excepción, mensaje y **traceback completo**.
- Al cliente: mensaje genérico + `correlation_id`, nada más.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Que los servicios lancen `HTTPException` directamente | Acopla la capa de negocio al transporte HTTP: la misma regla debería valer si la operación llegara por una cola de mensajes o un job programado. Además dispersa la decisión de qué código corresponde a cada situación, permitiendo que la misma condición devuelva 400 en un sitio y 409 en otro. |
| Devolver `str(exc)` en el cuerpo del error 500 | Filtra rutas de archivos, nombres de tablas y columnas, fragmentos de SQL y, en el peor caso, credenciales contenidas en una cadena de conexión. Es exactamente la fuga que el enunciado pide evitar. |
| Normalizar los errores de validación de 422 a 400 | 422 es semánticamente correcto (cuerpo sintácticamente válido pero semánticamente inválido) y es el comportamiento por defecto de FastAPI, reflejado en el esquema OpenAPI generado. Se cambia el *formato del cuerpo* para unificarlo, pero no el código. |
| Capturar y traducir excepciones en cada endpoint | Repite la misma decisión en N archivos; cambiar un criterio obligaría a modificar todos los routers en vez de una línea del mapa. |

## Consecuencias

**A favor:**
- El cliente implementa una sola rutina de manejo de errores.
- Cambiar el código HTTP de una situación de negocio es una línea de código.
- Verificado empíricamente que un fallo real (PostgreSQL detenido) devuelve al
  cliente únicamente `{"tipo":"error_interno", "correlation_id":"888f1d8e-..."}`
  mientras el log del servidor conserva el `OperationalError` con traceback
  completo bajo el mismo `correlation_id`.
- Los errores de dominio se registran como `WARNING` y no `ERROR`: un duplicado
  es un resultado esperado del negocio, no un fallo del sistema, y clasificarlo
  como error contaminaría las alertas operativas.

**Costo asumido:**
- Una capa de traducción adicional (excepción de dominio → código HTTP) que un
  enfoque directo no tendría. Se paga con desacoplamiento y consistencia.
- El formato propio no es exactamente `application/problem+json` del RFC (los
  nombres de campo están en español para ser coherentes con el resto del
  dominio). Si se requiriera interoperabilidad estricta con herramientas que
  consumen el RFC literal, habría que renombrar los campos.
