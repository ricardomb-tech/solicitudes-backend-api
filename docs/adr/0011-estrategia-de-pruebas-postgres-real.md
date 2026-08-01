# ADR-0011: Pruebas automatizadas contra PostgreSQL real, no SQLite ni mocks

- **Estado:** Aceptado
- **Fecha:** 2026-08-01
- **Bloque:** 4

## Contexto

El enunciado exige pruebas para creación válida, rechazo de datos inválidos,
manejo de duplicados, consulta de existentes/inexistentes, actualización de
estado y endpoints de salud. Hay que decidir contra qué base de datos correr
esas pruebas.

La opción más rápida de configurar es SQLite en memoria (no requiere levantar
ningún contenedor adicional, cada test arranca en milisegundos). Es también la
opción incorrecta para este proyecto.

## Decisión

Las pruebas corren contra una **base de datos PostgreSQL real** —el mismo
motor que se usa en desarrollo y el que se usaría en producción—, en una base
de datos separada (`solicitudes_test`) dentro del mismo contenedor `db` del
`docker-compose.yml`, creada y migrada automáticamente por la propia suite de
pruebas mediante el mismo Alembic de producción (no `Base.metadata.create_all()`).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| SQLite en memoria | No soporta `INSERT ... ON CONFLICT ... RETURNING` con la misma semántica que PostgreSQL, no aplica los `CHECK` de la misma forma, y su modelo de concurrencia (bloqueo de archivo completo) es radicalmente distinto al de PostgreSQL (MVCC). El mecanismo que este proyecto más necesita probar —la resolución atómica de duplicados bajo concurrencia (ADR-0003)— **no se puede verificar de forma fiel** en un motor distinto. Un test que pasa en SQLite y falla en producción es peor que no tener test: da una falsa sensación de cobertura. |
| Mockear la sesión de SQLAlchemy (dobles de prueba para toda la capa de datos) | Sirve para aislar la lógica de negocio pura, pero no puede probar lo que realmente importa aquí: si la restricción `UNIQUE` existe, si el `CHECK` de catálogo funciona, si `ON CONFLICT` resuelve la carrera. Mockear la base de datos para probar código cuyo comportamiento correcto *depende* de la base de datos es probar la simulación, no el sistema. |
| `Base.metadata.create_all()` para crear el esquema de pruebas en vez de migrar con Alembic | Crea una segunda fuente de verdad del esquema: si una migración tiene un error (un índice mal escrito, una restricción omitida), `create_all()` generaría el esquema "correcto" desde los modelos y el test pasaría igual, ocultando exactamente el tipo de error que Alembic existe para prevenir (ver ADR-0004). Ejecutar `alembic upgrade head` contra la base de pruebas verifica el artefacto real que se desplegaría. |
| Un contenedor de PostgreSQL efímero por ejecución de pruebas (`testcontainers`) | Es una opción robusta y común en otros contextos, pero añade una dependencia de Docker-en-Docker (el proceso de pruebas necesitaría acceso al socket de Docker del host), lo cual complica la ejecución en Windows y no aporta beneficio sobre reutilizar el contenedor `db` que el propio `docker-compose.yml` ya expone en la misma red. |

## Cómo se implementó

1. Un stage `test` en el Dockerfile del backend (ver `docs/adr/0012`) instala
   `pytest`, `pytest-cov` y `httpx` sobre la misma imagen base que producción.
2. Al iniciar la sesión de pruebas, `conftest.py` se conecta a la base de datos
   administrativa (`postgres`) del mismo servidor, crea `solicitudes_test` si
   no existe, y ejecuta `alembic upgrade head` contra ella mediante un
   subproceso con `DATABASE_URL` sobrescrita solo para esa invocación —sin
   tocar la configuración cacheada de la aplicación.
3. Cada prueba se ejecuta con la tabla limpia (`TRUNCATE ... RESTART IDENTITY
   CASCADE` en un *fixture* automático al finalizar cada test).
4. El test de concurrencia (ADR-0003) usa hilos con sesiones y conexiones
   independientes contra esta misma base de datos real — es la única forma de
   que la prueba signifique algo: la garantía de atomicidad la da PostgreSQL,
   no el código Python.

## Consecuencias

**A favor:**
- Las pruebas verifican el comportamiento real del sistema, no una
  aproximación. Un test en verde es evidencia genuina de que el código
  funciona contra el motor que se va a desplegar.
- El test de concurrencia reproduce fielmente el escenario de dos procesos de
  la aplicación compitiendo por el mismo identificador externo.
- No se requiere infraestructura adicional a la que el proyecto ya define: se
  reutiliza el mismo servicio `db` del `docker-compose.yml`.

**Costo asumido:**
- Las pruebas son más lentas que con SQLite en memoria (hay conexión de red
  real, aunque sea dentro de la misma red de Docker) y requieren que el
  contenedor `db` esté disponible — no se pueden ejecutar de forma
  verdaderamente aislada sin Docker. Se acepta porque el proyecto entero está
  diseñado para ejecutarse en contenedores; exigir que las pruebas también lo
  hagan es consistente con esa premisa, no una limitación añadida.
