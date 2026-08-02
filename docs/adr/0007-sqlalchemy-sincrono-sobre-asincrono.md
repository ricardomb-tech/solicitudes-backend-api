# ADR-0007: SQLAlchemy síncrono (no asíncrono) con endpoints `def`

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 2

> **En pocas palabras:** los endpoints se declaran con `def` (no `async def`), y SQLAlchemy usa `Session` síncrona (no `AsyncSession`). Cuando FastAPI ve un handler `def`, lo corre en un threadpool separado del event loop — la base de datos bloquea el hilo, no el event loop. La concurrencia se conserva sin la complejidad del modo asíncrono.

## Contexto

FastAPI es un framework ASGI construido sobre un event loop asíncrono, y SQLAlchemy 2.0 ofrece tanto una API síncrona (`Session`, `create_engine`) como una asíncrona (`AsyncSession`, `create_async_engine`). Hay que elegir cuál usar.

El argumento habitual a favor de `async` es: "una llamada bloqueante a la base de datos bloquea el event loop y mata la concurrencia". Ese argumento es correcto **solo si** el handler se declara `async def` y dentro se ejecuta código bloqueante. Si el handler se declara `def`, FastAPI lo ejecuta en un threadpool separado — la llamada a la base de datos bloquea el hilo de trabajo, pero el event loop queda libre para seguir atendiendo otras peticiones.

## Decisión

Se usa **SQLAlchemy síncrono** (`Session` + `create_engine`) con el driver `psycopg` (v3), y los endpoints de FastAPI se declaran con `def`, no con `async def`.

Cuando un handler es `def`, FastAPI (a través de Starlette/AnyIO) lo ejecuta automáticamente en un threadpool con hasta 40 hilos concurrentes por defecto. La operación bloqueante de base de datos ocurre en un hilo trabajador; el event loop queda libre. La concurrencia se conserva — el límite pasa a ser el tamaño del threadpool, no la ausencia de asincronía.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `AsyncSession` + `create_async_engine` + endpoints `async def` | Es la opción idiomática "moderna" y sería técnicamente correcta. Pero introduce una clase de fallos que no existe en el modo síncrono: errores de `MissingGreenlet` al acceder a atributos fuera del contexto async, lazy loading que falla silenciosamente, sesiones compartidas accidentalmente entre tareas concurrentes. Con tres días de plazo, ese riesgo de depuración no se compensa con ningún beneficio medible a la escala de esta prueba. |
| Endpoints `async def` pero con `Session` síncrona dentro | **Este sí sería un error real.** El handler corre en el event loop, y la llamada bloqueante a la base de datos lo bloquea para todas las demás peticiones simultáneas. Es exactamente el antipatrón que el argumento a favor de async describe. Se menciona explícitamente aquí porque la diferencia entre "handlers `def` + SQLAlchemy síncrono" y "handlers `async def` + SQLAlchemy síncrono" es el punto que más hay que entender — uno es correcto, el otro es un cuello de botella. |

## Consecuencias

**Lo que se gana:**
- Menos superficie de error: sin greenlets, sin contextos async que puedan filtrarse entre peticiones.
- Alembic funciona con la configuración estándar, sin plantilla asíncrona adicional.
- Las pruebas se escriben con `TestClient` y `pytest` normales, sin `pytest-asyncio` ni gestión manual del event loop.
- El mismo driver (`psycopg` v3) sirve para la aplicación y para Alembic — no hay que arrastrar dos drivers distintos (`asyncpg` + `psycopg2`) en la misma imagen.

**Lo que se paga:**
- El throughput máximo queda acotado por el tamaño del threadpool de AnyIO (40 hilos por defecto). En un servicio con miles de peticiones de I/O de red de alta latencia, `async` escalaría mejor. A la escala de este servicio — gestión de solicitudes institucionales, cuello de botella real en PostgreSQL — ese límite no se alcanza.
- **Cuándo revisar esta decisión:** si el servicio incorporara llamadas salientes a APIs externas con alta latencia dentro del ciclo de petición (donde el hilo quedaría ocioso esperando red), el balance cambiaría a favor de `async`. Se registraría entonces un nuevo ADR que reemplazara a este.
