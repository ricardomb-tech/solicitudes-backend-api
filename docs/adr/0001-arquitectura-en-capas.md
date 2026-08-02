# ADR-0001: Arquitectura en capas (router / service / repository)

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 0 (planeación) — implementación distribuida en Bloques 2 y 3

> **En pocas palabras:** el código se divide en cuatro capas con una regla sencilla —cada capa solo habla con la de al lado— para que las reglas de negocio se puedan probar sin levantar un servidor y para que cambiar la base de datos no obligue a tocar los endpoints.

## Contexto

El enunciado exige explícitamente "separación entre rutas, lógica de negocio y acceso a datos". Sin esa separación, el código termina mezclado en el mismo archivo: la validación de unicidad junto al `router.post(...)`, la lógica de transición de estados junto al `session.query(...)`. El resultado es código que solo se puede probar arrancando el servidor completo, donde un cambio en una regla de negocio obliga a tocar el endpoint, y donde nadie sabe bien quién es responsable de qué.

## Decisión

Cuatro capas, con una regla mecánica que permite verificar que la separación es real y no solo decorativa:

```
api/routers/    → HTTP puro: parsea el request, llama al servicio, serializa la respuesta.
services/       → reglas de negocio: unicidad, transiciones de estado, orquestación.
repositories/   → única capa que conoce SQLAlchemy y SQL.
models/         → definición del ORM.
```

**La regla de verificación:** el router nunca importa `sqlalchemy`; el service nunca importa `fastapi`. Si ambas condiciones se cumplen, la separación es genuina. Si no, hay algo mezclado que debería estar separado.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Todo en el router (estilo "demo rápida") | Funciona para 2 endpoints y sin reglas de negocio. Para los ~10 endpoints de esta prueba, con unicidad, máquina de estados y manejo de concurrencia, termina siendo un monolito dentro del archivo del router: imposible de testear sin HTTP, imposible de modificar una regla sin tocar el endpoint. |
| Capas adicionales (Unit of Work explícito, CQRS, arquitectura hexagonal) | Sobre-ingeniería real para el alcance de esta prueba: un solo agregado (`Solicitud`), un caso de uso de lectura y tres de escritura. El tiempo invertido en puertos y adaptadores no se ve en la evaluación; el tiempo invertido en profundidad sobre concurrencia, errores y reintentos sí. |

## Consecuencias

**Lo que se gana:**
- Los tests de `services/` se pueden correr con dobles del repositorio, sin base de datos real.
- Los tests de `repositories/` corren contra Postgres real sin pasar por HTTP.
- Cada capa se prueba con el mínimo de infraestructura que su responsabilidad requiere.
- Un cambio hipotético de ORM (SQLAlchemy → otro) solo tocaría `repositories/` — el servicio y el router no sabrían que algo cambió.

**Lo que se paga:**
- Más archivos e indirección que un CRUD de un solo archivo. Para una prueba con reglas de negocio reales (máquina de estados, concurrencia atómica), ese costo se paga solo. Para un CRUD trivial no lo valdría —y se documenta así deliberadamente para no presentar la arquitectura en capas como "la respuesta correcta siempre", porque no lo es.
