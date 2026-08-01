# ADR-0004: Alembic en lugar de script SQL plano para versionar el esquema

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 0 (planeación) — implementación en Bloque 2

## Contexto

El enunciado pide "script de inicialización o migraciones de base de datos" y
señala explícitamente que "el uso de Alembic será valorado positivamente". Hay
que decidir entre un script `init.sql` montado en el `docker-entrypoint-initdb.d`
de la imagen oficial de Postgres, o Alembic como herramienta de migraciones
versionadas.

## Decisión

Se usa **Alembic** con una migración inicial (`alembic revision
--autogenerate`) ejecutada como parte del arranque del contenedor backend
(`alembic upgrade head && uvicorn ...`), no como script de inicialización de
Postgres.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `init.sql` montado en `/docker-entrypoint-initdb.d/` | Solo se ejecuta la **primera vez** que el volumen de datos está vacío. Si el esquema cambia después (se agrega una columna, se ajusta un `CHECK`), el script no vuelve a ejecutarse contra un volumen ya inicializado — el cambio se pierde silenciosamente a menos que se borre el volumen (perdiendo los datos). No es una estrategia de migración real, solo de bootstrap inicial. |
| Ejecutar `CREATE TABLE IF NOT EXISTS` desde el propio código de la aplicación al arrancar | No versiona el historial de cambios de esquema, no soporta `downgrade` (rollback), y mezcla responsabilidad de la aplicación (servir requests) con la de gestionar el ciclo de vida del esquema. |

## Consecuencias

**A favor:**
- Cada cambio de esquema queda versionado como un archivo de migración con
  `upgrade()`/`downgrade()`, revisable en el historial de commits — coherente
  con el requisito de "historial de commits descriptivos".
- Es exactamente el mecanismo que se usaría en un entorno real (y en AWS): un
  paso de migración explícito antes o durante el despliegue, no un efecto
  secundario del arranque de la aplicación.
- Facilita el ejercicio de "modificación menor en vivo" de la sustentación:
  agregar un campo o ajustar un catálogo es `alembic revision --autogenerate`
  + revisión manual del SQL generado, un flujo de minutos.

**Costo asumido:**
- Una pieza más de configuración que aprender/mantener (`alembic.ini`,
  `env.py`) frente a un `.sql` plano. Se considera justificado porque el
  propio enunciado marca esta herramienta como valorada positivamente y
  porque el proyecto sí tiene evolución de esquema esperable (agregar
  catálogos, campos) durante la prueba y la sustentación.
