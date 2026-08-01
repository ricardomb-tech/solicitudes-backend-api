# Architecture Decision Records (ADR)

## ¿Qué es un ADR y por qué se usa aquí?

Un ADR es un documento corto que registra **una** decisión de arquitectura
significativa: el problema que la origina, la opción elegida, las alternativas
consideradas y por qué se descartaron, y las consecuencias (incluidas las
negativas) de vivir con esa decisión. El formato es el propuesto originalmente
por Michael Nygard y es el estándar de facto en la industria.

**Por qué un ADR y no solo "explicarlo en el README":**

- Es **citable**: una decisión tiene un número (`ADR-0003`) que se puede
  referenciar desde el código, un PR, un test o la sustentación oral, sin
  repetir la justificación completa cada vez.
- Es **inmutable en el tiempo**: un ADR aceptado no se edita para reflejar un
  cambio de opinión futuro; si la decisión cambia, se crea un ADR nuevo con
  estado `Reemplaza a ADR-000X`, y el original pasa a `Reemplazado por
  ADR-000Y`. Esto preserva el historial de *por qué* se pensaba distinto antes
  — información valiosa que un README que "simplemente se actualiza" pierde.
- **Filtra ruido**: no todo es un ADR. Se documenta aquí solo lo que es difícil
  o costoso de revertir y tiene alternativas reales que alguien podría
  razonablemente preferir. Decisiones de estilo o detalles de implementación
  van en comentarios de código o en la bitácora (`docs/DECISIONES.md`), no aquí.

## Plantilla

```markdown
# ADR-XXXX: Título en forma de decisión tomada

- **Estado:** Propuesto | Aceptado | Reemplazado por ADR-YYYY
- **Fecha:** AAAA-MM-DD
- **Bloque:** referencia al bloque de trabajo donde se tomó

## Contexto
¿Qué problema u obligación del enunciado origina esta decisión?

## Decisión
Qué se decidió, en una frase clara.

## Alternativas consideradas
| Alternativa | Por qué se descartó |

## Consecuencias
Lo que se gana y lo que se paga (siempre hay un costo; nombrarlo es parte de
la honestidad técnica del documento).
```

## Índice de decisiones

| ADR | Título | Estado | Bloque |
|---|---|---|---|
| [0001](0001-arquitectura-en-capas.md) | Arquitectura en capas (router / service / repository) | Aceptado | 0 |
| [0002](0002-uuid-como-identificador-interno.md) | UUID como identificador interno, distinto del identificador externo | Aceptado | 0 |
| [0003](0003-concurrencia-restriccion-unica-on-conflict.md) | Concurrencia sobre `identificador_externo` resuelta con restricción única + `ON CONFLICT` en BD | Aceptado | 0 (implementación en Bloque 2) |
| [0004](0004-alembic-para-migraciones.md) | Alembic en lugar de script SQL plano para versionar el esquema | Aceptado | 0 (implementación en Bloque 2) |
| [0005](0005-healthcheck-y-orden-inicializacion.md) | Healthcheck de Postgres + `depends_on: condition: service_healthy` | Aceptado | 1 |
| [0006](0006-docker-multistage-no-root.md) | Imagen Docker multi-stage con usuario no-root | Aceptado | 1 |
| [0007](0007-sqlalchemy-sincrono-sobre-asincrono.md) | SQLAlchemy síncrono (no asíncrono) con endpoints `def` | Aceptado | 2 |
| [0008](0008-contrato-uniforme-de-errores.md) | Contrato uniforme de errores y no exposición de detalles técnicos | Aceptado | 3 |
| [0009](0009-observabilidad-logs-json-correlacion.md) | Logs estructurados JSON con identificador de correlación propagado | Aceptado | 3 |
| [0010](0010-liveness-readiness-separados.md) | Endpoints de liveness y readiness separados | Aceptado | 3 |

> Se agregan nuevos ADR a medida que se toman decisiones equivalentes en los
> bloques siguientes (formato de errores, máquina de estados, política de
> reintentos del consumidor, ALB vs. API Gateway en AWS, etc.).
