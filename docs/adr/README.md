# Architecture Decision Records (ADR)

## ¿Qué es un ADR y para qué sirve?

Un ADR es un documento corto que registra **una** decisión de arquitectura significativa: el problema que la origina, la opción elegida, las alternativas consideradas y por qué se descartaron, y las consecuencias (incluidas las negativas) de vivir con esa decisión.

La clave está en esa última parte — las consecuencias negativas. Un ADR honesto no vende la decisión tomada como perfecta; documenta qué se ganó y qué se pagó, para que quien llegue después (o quien revise el código en la sustentación) entienda que hubo criterio detrás, no solo intuición.

**Por qué un ADR y no solo "explicarlo en el README":**

- **Es citable.** Una decisión tiene un número (`ADR-0003`) que se puede referenciar desde el código, un PR, un test o la sustentación oral, sin repetir la justificación completa cada vez. Cuando en el código dice "ver ADR-0007", hay un documento que responde *exactamente* la pregunta que ese comentario anticipa.

- **Preserva el historial.** Un ADR aceptado no se edita para reflejar un cambio de opinión futuro. Si la decisión cambia, se escribe un ADR nuevo con estado `Reemplaza a ADR-000X`, y el original pasa a `Reemplazado por ADR-000Y`. Así se conserva el registro de *por qué se pensaba distinto antes* — información que un README "que simplemente se actualiza" pierde para siempre.

- **Filtra ruido.** No todo es un ADR. Solo se documenta aquí lo que es difícil o costoso de revertir y tiene alternativas reales que alguien podría razonablemente preferir. Decisiones de estilo o detalles de implementación van en comentarios de código, no aquí.

## Plantilla

```markdown
# ADR-XXXX: Título en forma de decisión tomada

- **Estado:** Propuesto | Aceptado | Reemplazado por ADR-YYYY
- **Fecha:** AAAA-MM-DD
- **Bloque:** referencia al bloque de trabajo donde se tomó

> **En pocas palabras:** una frase que cualquiera pueda entender.

## Contexto
¿Qué problema u obligación del enunciado origina esta decisión? ¿Qué pasaría si no se tomara?

## Decisión
Qué se decidió, en términos concretos.

## Alternativas consideradas
| Alternativa | Por qué se descartó |

## Consecuencias
Lo que se gana y lo que se paga. Siempre hay un costo; nombrarlo es parte de la honestidad técnica del documento.
```

## Índice de decisiones

| ADR | Título | Estado | Bloque |
|---|---|---|---|
| [0001](0001-arquitectura-en-capas.md) | Arquitectura en capas (router / service / repository) | Aceptado | 0 |
| [0002](0002-uuid-como-identificador-interno.md) | UUID como identificador interno, distinto del identificador externo | Aceptado | 0 |
| [0003](0003-concurrencia-restriccion-unica-on-conflict.md) | Concurrencia sobre `identificador_externo` resuelta con restricción única + `ON CONFLICT` en BD | Aceptado | 0 |
| [0004](0004-alembic-para-migraciones.md) | Alembic en lugar de script SQL plano para versionar el esquema | Aceptado | 0 |
| [0005](0005-healthcheck-y-orden-inicializacion.md) | Healthcheck de Postgres + `depends_on: condition: service_healthy` | Aceptado | 1 |
| [0006](0006-docker-multistage-no-root.md) | Imagen Docker multi-stage con usuario no-root | Aceptado | 1 |
| [0007](0007-sqlalchemy-sincrono-sobre-asincrono.md) | SQLAlchemy síncrono (no asíncrono) con endpoints `def` | Aceptado | 2 |
| [0008](0008-contrato-uniforme-de-errores.md) | Contrato uniforme de errores y no exposición de detalles técnicos | Aceptado | 3 |
| [0009](0009-observabilidad-logs-json-correlacion.md) | Logs estructurados JSON con identificador de correlación propagado | Aceptado | 3 |
| [0010](0010-liveness-readiness-separados.md) | Endpoints de liveness y readiness separados | Aceptado | 3 |
| [0011](0011-estrategia-de-pruebas-postgres-real.md) | Pruebas automatizadas contra PostgreSQL real, no SQLite ni mocks | Aceptado | 4 |
| [0012](0012-stage-de-pruebas-en-dockerfile.md) | Stage `test` independiente en el Dockerfile, excluido de producción | Aceptado | 4 |
| [0013](0013-politica-de-reintentos-consumidor.md) | Clasificación transitorio/definitivo y backoff exponencial con jitter | Aceptado | 5 |
| [0014](0014-consumidor-un-solo-lote.md) | El consumidor procesa un solo lote y termina (no es un bucle continuo) | Aceptado | 5 |
| [0015](0015-defaults-en-compose-y-binding-localhost.md) | Valores por defecto en `docker-compose.yml` y publicación solo en localhost | Aceptado | Auditoría |
| [0016](0016-duplicacion-deliberada-entre-servicios.md) | Duplicación deliberada de catálogos entre backend y consumidor | Aceptado | Auditoría |
| [0017](0017-maquina-de-estados-de-la-solicitud.md) | Máquina de estados explícita para el ciclo de vida de la solicitud | Aceptado | 2 |

> La justificación de ALB sobre API Gateway está en `docs/aws/PROPUESTA-AWS.md` (sección "Servicios y función de cada uno"), no como ADR aparte: es una decisión de la propuesta de despliegue, no del código de este repositorio.
