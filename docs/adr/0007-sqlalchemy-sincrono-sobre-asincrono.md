# ADR-0007: SQLAlchemy síncrono (no asíncrono) con endpoints `def`

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 2

## Contexto

FastAPI es un framework ASGI construido sobre un *event loop* asíncrono, y
SQLAlchemy 2.0 ofrece tanto una API síncrona (`Session`, `create_engine`) como
una asíncrona (`AsyncSession`, `create_async_engine`). Hay que elegir cuál usar
para la capa de acceso a datos.

El argumento habitual a favor de `async` es que "una llamada bloqueante a la
base de datos bloquea el *event loop* y mata la concurrencia". Ese argumento es
cierto **solo si** el handler se declara `async def` y dentro se ejecuta código
bloqueante. No es cierto si el handler se declara `def`.

## Decisión

Se usa **SQLAlchemy síncrono** (`Session` + `create_engine`) con el driver
`psycopg` (v3), y los endpoints de FastAPI se declaran con `def`, no con
`async def`.

Cuando un handler se declara `def`, FastAPI (a través de Starlette/AnyIO) lo
ejecuta automáticamente en un **threadpool** separado del *event loop*. La
operación bloqueante de base de datos ocurre en un hilo trabajador; el *event
loop* queda libre para atender otras peticiones. La concurrencia se conserva —
el límite pasa a ser el tamaño del threadpool (40 hilos por defecto en AnyIO),
no la ausencia de asincronía.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `AsyncSession` + `create_async_engine` + endpoints `async def` | Es la opción idiomática "moderna" y sería correcta, pero introduce una clase de fallos que no existe en el modo síncrono: errores de `MissingGreenlet` al acceder a atributos fuera del contexto async, *lazy loading* que falla silenciosamente, y sesiones compartidas accidentalmente entre tareas concurrentes. Con un plazo de tres días, ese riesgo de depuración no se compensa con ningún beneficio medible a la escala de esta prueba. Además, Alembic requiere configuración adicional (plantilla `async`) para trabajar contra un motor asíncrono. |
| Endpoints `async def` pero con `Session` síncrona dentro | **Esta sí sería un error real**: el handler corre en el *event loop* y la llamada bloqueante a la BD lo bloquea para todas las demás peticiones. Es el antipatrón que el argumento a favor de async describe correctamente. Se menciona explícitamente aquí porque la diferencia entre esta opción y la decisión tomada es exactamente el punto que hay que entender. |

## Consecuencias

**A favor:**
- Menos superficie de error: no hay *greenlets*, no hay contextos async que
  puedan filtrarse entre peticiones.
- Alembic funciona con la configuración estándar, sin plantilla asíncrona.
- Las pruebas se escriben con `TestClient` y `pytest` normales, sin
  `pytest-asyncio` ni gestión manual del *event loop*.
- El mismo driver (`psycopg` v3) sirve para la aplicación y para Alembic,
  evitando arrastrar dos drivers distintos (p. ej. `asyncpg` + `psycopg2`) en
  la misma imagen.

**Costo asumido:**
- El throughput máximo queda acotado por el tamaño del threadpool de AnyIO
  (40 hilos concurrentes por defecto, configurable). En un servicio con miles
  de peticiones concurrentes de I/O prolongada, `async` escalaría mejor con
  menos memoria por conexión. A la escala de este servicio (gestión de
  solicitudes institucionales, con el cuello de botella real en PostgreSQL y
  no en el número de hilos de Python), ese límite no se alcanza.
- **Cuándo se revisaría esta decisión:** si el servicio incorporara llamadas
  salientes a APIs externas con latencia alta dentro del ciclo de la petición
  (donde el hilo quedaría ocioso esperando I/O de red), el balance cambiaría a
  favor de `async`. Se registraría entonces un ADR nuevo que reemplace a este.
