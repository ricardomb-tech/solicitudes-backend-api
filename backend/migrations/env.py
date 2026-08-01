"""
Configuración de entorno de Alembic.

Dos decisiones relevantes en este archivo:

1. La URL de conexión se toma de `Settings` (variable de entorno
   DATABASE_URL), NO de `alembic.ini`. Así las credenciales nunca quedan
   escritas en un archivo versionado, y las migraciones apuntan a la misma
   base de datos que la aplicación sin duplicar configuración.

2. Se importa `app.models` para que `Base.metadata` conozca todas las tablas
   antes de comparar contra el esquema real. Sin esa importación,
   `--autogenerate` no vería ningún modelo y generaría una migración vacía —
   un fallo silencioso y difícil de diagnosticar.

3. `run_migrations_online` toma un advisory lock de PostgreSQL antes de
   aplicar cualquier migración. Contrario a lo que un comentario anterior de
   `entrypoint.sh` afirmaba, Alembic NO serializa migraciones concurrentes
   por sí solo (su bloqueo de fila sobre `alembic_version` ocurre en el
   UPDATE final, DESPUÉS del DDL). Sin este lock, si dos réplicas del backend
   arrancaran a la vez tras un despliegue con una migración nueva, ambas
   ejecutarían el mismo DDL y la segunda fallaría al hacer commit
   (`DuplicateTable`/`DuplicateObject`), tumbando esa réplica por `set -e` en
   el entrypoint. Con el lock, la segunda simplemente espera a la primera y,
   al ver que ya está en `head`, no hace nada.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# Clave arbitraria pero fija para el advisory lock de esta aplicación. Puede
# ser cualquier bigint; lo único que importa es que sea la MISMA en todas las
# réplicas para que efectivamente se serialicen entre sí.
_CLAVE_LOCK_MIGRACIONES = 721839

from app.core.config import get_settings
from app.db.base import Base

# Importar los modelos registra las tablas en Base.metadata (efecto necesario
# para --autogenerate). El import se mantiene aunque no se use directamente.
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inyecta la URL real en tiempo de ejecución (ver decisión 1 arriba).
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL de las migraciones sin conectarse a la base de datos."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # compare_type: detecta cambios de tipo de columna al autogenerar.
        # Desactivado por defecto en Alembic; activarlo evita que un cambio de
        # VARCHAR(64) a VARCHAR(128) pase desapercibido.
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones contra una conexión real."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            # pg_advisory_xact_lock: bloqueo a nivel de transacción, se
            # libera automáticamente al hacer commit o rollback — no requiere
            # un "unlock" explícito ni arriesga quedar retenido si el proceso
            # muere a mitad de la migración.
            connection.execute(text("SELECT pg_advisory_xact_lock(:clave)"),
                                {"clave": _CLAVE_LOCK_MIGRACIONES})
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
