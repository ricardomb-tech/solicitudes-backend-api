# ADR-0001: Arquitectura en capas (router / service / repository)

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 0 (planeación) — implementación distribuida en Bloques 2 y 3

## Contexto

El enunciado exige "separación entre rutas, lógica de negocio y acceso a
datos" (requisito técnico explícito), además de reglas de negocio no triviales
que deben poder probarse de forma aislada: unicidad del identificador externo,
transición de estados, formato de errores. Si esas reglas viven mezcladas con
el código HTTP de FastAPI, no se pueden testear sin levantar un servidor, y un
cambio en la política de un caso de uso obliga a tocar el endpoint.

## Decisión

Se adopta una arquitectura en cuatro capas, con una regla mecánica de
verificación (no solo una convención de carpetas):

```
api/routers/    → HTTP puro: parsea request, delega, serializa response.
services/       → reglas de negocio: unicidad, transiciones de estado, orquestación.
repositories/   → única capa que conoce SQLAlchemy / SQL.
models/         → definición del ORM.
```

**Regla de verificación:** el router nunca importa `sqlalchemy`; el service
nunca importa `fastapi`. Si se cumple, la separación es real y no decorativa.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Todo en el router (estilo script, común en demos rápidas) | Imposible de testear sin HTTP; cualquier cambio de regla de negocio obliga a tocar el endpoint; no escala a los ~10 endpoints y reglas de esta prueba. |
| Capas adicionales (UoW explícito, CQRS, arquitectura hexagonal completa con puertos/adaptadores) | Sobre-ingeniería para el alcance de la prueba (un solo agregado, `Solicitud`); el tiempo se invierte mejor en profundidad sobre lo pedido (concurrencia, errores, retries) que en capas que nadie va a ejercitar. |

## Consecuencias

**A favor:**
- Los tests de `services/` corren sin base de datos real usando dobles del
  repositorio, y los de `repositories/` corren contra Postgres real sin pasar
  por HTTP — cada capa se prueba con el mínimo de infraestructura necesaria.
- Un cambio en cómo se persiste (SQLAlchemy → otro ORM, hipotéticamente) solo
  tocaría `repositories/`.

**Costo asumido:**
- Más archivos e indirección que un CRUD de un solo archivo. Para una prueba
  con reglas de negocio reales (máquina de estados, concurrencia), ese costo
  se paga solo; para un CRUD trivial no lo valdría, y así se documenta para no
  aparentar que la arquitectura en capas es "la respuesta correcta siempre".
