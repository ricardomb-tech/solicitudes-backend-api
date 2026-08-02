# ADR-0004: Alembic en lugar de script SQL plano para versionar el esquema

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 0 (planeación) — implementación en Bloque 2

> **En pocas palabras:** los cambios de esquema de la base de datos se versionan con Alembic (como migraciones numeradas con `upgrade` y `downgrade`), no con un script SQL que solo se ejecuta una vez. Así, agregar una columna en vivo —durante la sustentación, por ejemplo— es escribir una migración, no borrar y recrear el volumen.

## Contexto

El enunciado pide "script de inicialización o migraciones de base de datos" y señala explícitamente que "el uso de Alembic será valorado positivamente". Hay que elegir entre un script `init.sql` montado en el `docker-entrypoint-initdb.d` de la imagen de Postgres, o Alembic como herramienta de migraciones versionadas.

La diferencia práctica no es trivial: un script de inicialización solo se ejecuta la primera vez que el volumen de datos está vacío. Si el esquema cambia después —se agrega una columna, se ajusta un `CHECK`, se crea un índice nuevo— el script no vuelve a ejecutarse contra un volumen ya inicializado. El cambio se pierde silenciosamente a menos que se borre el volumen (perdiendo los datos). Eso no es una estrategia de migración; es un bootstrap de uso único.

## Decisión

Se usa **Alembic** con una migración inicial ejecutada como parte del arranque del contenedor backend (`alembic upgrade head && uvicorn ...`), no como script de inicialización de Postgres.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `init.sql` en `/docker-entrypoint-initdb.d/` | Solo se ejecuta la primera vez que el volumen está vacío. Si el esquema evoluciona (una columna nueva, un índice ajustado), el script no vuelve a correr contra un volumen ya inicializado — el cambio se pierde sin ningún aviso. No es migración, es bootstrap de un solo uso. |
| `CREATE TABLE IF NOT EXISTS` desde el código de la aplicación al arrancar | No versiona el historial de cambios, no soporta `downgrade`, y mezcla la responsabilidad de la aplicación (atender requests) con la de gestionar el ciclo de vida del esquema de la base de datos. Dos responsabilidades en un solo lugar que no se deben mezclar. |

## Consecuencias

**Lo que se gana:**
- Cada cambio de esquema queda versionado como un archivo de migración con `upgrade()` y `downgrade()`, revisable en el historial de commits — coherente con el requisito de "historial de commits descriptivos".
- Agregar un campo o ajustar un catálogo durante la sustentación es `alembic revision --autogenerate` + revisión manual del SQL generado, un flujo de minutos.
- Es el mecanismo que se usaría en producción real (y en AWS): un paso de migración explícito antes o durante el despliegue, no un efecto secundario del arranque de la aplicación.

**Lo que se paga:**
- Una pieza más de configuración (`alembic.ini`, `env.py`) frente a un script SQL plano. Se considera justificado porque el propio enunciado marca esta herramienta como valorada positivamente, y porque el proyecto sí tiene evolución de esquema esperable durante la prueba.

**Advertencia importante sobre `--autogenerate`:** Alembic detecta automáticamente cambios en tablas, columnas e índices, pero **no** detecta cambios en restricciones `CHECK`. Agregar un valor a un catálogo (`TipoSolicitud`, `Prioridad`, `EstadoSolicitud`) y correr `--autogenerate` genera una migración vacía sin avisar del cambio omitido. El paso manual obligatorio está documentado en `app/models/solicitud.py::_check_en_catalogo`.
