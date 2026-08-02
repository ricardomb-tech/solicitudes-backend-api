# ADR-0011: Pruebas automatizadas contra PostgreSQL real, no SQLite ni mocks

- **Estado:** Aceptado
- **Fecha:** 2026-08-01
- **Bloque:** 4

> **En pocas palabras:** las pruebas corren contra PostgreSQL real — el mismo motor que producción — porque el comportamiento más importante que hay que probar (la resolución atómica de duplicados bajo concurrencia) no se puede verificar de forma fiel en un motor distinto. Un test que pasa en SQLite y falla en producción es peor que no tener test.

## Contexto

El enunciado exige pruebas para creación válida, rechazo de datos inválidos, manejo de duplicados, consulta de existentes e inexistentes, actualización de estado y endpoints de salud. Hay que decidir contra qué base de datos corren esas pruebas.

La opción más rápida de configurar es SQLite en memoria: no requiere levantar ningún contenedor adicional, cada test arranca en milisegundos. Es también la opción incorrecta para este proyecto, y se descarta con argumentos concretos, no por preferencia.

## Decisión

Las pruebas corren contra una **base de datos PostgreSQL real** — el mismo motor que desarrollo y producción — en una base de datos separada (`solicitudes_test`) dentro del mismo contenedor `db` del `docker-compose.yml`. El esquema se crea ejecutando `alembic upgrade head` contra esa base de datos, no con `Base.metadata.create_all()`.

## Cómo funciona

1. Un stage `test` en el Dockerfile instala `pytest`, `pytest-cov` e `httpx` sobre la misma imagen base que producción (ver ADR-0012).
2. Al iniciar la sesión de pruebas, `conftest.py` se conecta a la base de datos administrativa (`postgres`) del mismo servidor, crea `solicitudes_test` si no existe, y ejecuta `alembic upgrade head` contra ella mediante un subproceso con `DATABASE_URL` sobrescrita solo para esa invocación.
3. Cada prueba termina con la tabla limpia (`TRUNCATE ... RESTART IDENTITY CASCADE` en un fixture automático al finalizar cada test).
4. El test de concurrencia (ADR-0003) lanza 20 hilos con sesiones y conexiones independientes contra esta base de datos real — es la única forma de que la prueba signifique algo.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| SQLite en memoria | No soporta `INSERT ... ON CONFLICT ... RETURNING` con la misma semántica que PostgreSQL, no aplica los `CHECK` de la misma forma, y su modelo de concurrencia (bloqueo de archivo completo) es radicalmente distinto al MVCC de PostgreSQL. El mecanismo que más necesita verificación — la resolución atómica de duplicados — no se puede probar de forma fiel en un motor diferente. Un test que pasa en SQLite y falla en producción da una falsa sensación de cobertura. |
| Mockear la sesión de SQLAlchemy | Sirve para aislar lógica de negocio pura, pero no puede verificar si la restricción `UNIQUE` existe, si el `CHECK` de catálogo funciona o si `ON CONFLICT` resuelve la carrera. Mockear la base de datos para probar código cuyo comportamiento correcto *depende* de la base de datos es probar la simulación, no el sistema. |
| `Base.metadata.create_all()` en vez de Alembic para crear el esquema de pruebas | Crea una segunda fuente de verdad del esquema: si una migración tiene un error (un índice mal escrito, una restricción omitida), `create_all()` generaría el esquema "correcto" desde los modelos y el test pasaría igual, ocultando exactamente el tipo de error que Alembic existe para prevenir (ver ADR-0004). |
| Contenedor de PostgreSQL efímero por ejecución (`testcontainers`) | Opción robusta en otros contextos, pero añade acceso al socket de Docker del host (Docker-en-Docker), lo que complica la ejecución en Windows y en CI sin privilegios. No aporta beneficio sobre reutilizar el contenedor `db` que el `docker-compose.yml` ya expone en la misma red. |

## Consecuencias

**Lo que se gana:**
- Las pruebas verifican el comportamiento real del sistema, no una aproximación. Un test en verde es evidencia genuina de que el código funciona contra el motor que se va a desplegar.
- El test de concurrencia reproduce fielmente el escenario de dos procesos compitiendo por el mismo identificador externo — solo es posible contra un motor que implemente MVCC real.
- No se requiere infraestructura adicional: se reutiliza el mismo servicio `db` del `docker-compose.yml`.

**Lo que se paga:**
- Las pruebas son más lentas que con SQLite en memoria (hay conexión de red real, aunque sea dentro de Docker) y requieren que el contenedor `db` esté disponible. Se acepta porque el proyecto entero está diseñado para ejecutarse en contenedores: exigir que las pruebas también lo hagan es consistente con esa premisa, no una limitación añadida.
