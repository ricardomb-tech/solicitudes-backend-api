#!/bin/sh
# =============================================================================
# Entrypoint del backend.
#
# Aplica las migraciones pendientes ANTES de arrancar el servidor: la
# aplicación nunca debe atender peticiones contra un esquema desactualizado.
#
# `set -e` hace que el script aborte si `alembic upgrade` falla, en lugar de
# arrancar igualmente una API que fallará en la primera consulta. Es preferible
# que el contenedor no arranque (fallo visible e inmediato) a que arranque
# "sano" y devuelva errores en tiempo de ejecución.
#
# Nota sobre entornos productivos: en AWS este paso se ejecutaría como una
# tarea de migración independiente y previa al despliegue, no en el arranque de
# cada réplica — de lo contrario N réplicas intentarían migrar en paralelo.
# Alembic toma un bloqueo sobre su tabla de versiones, así que es seguro, pero
# separar el paso hace el despliegue más explícito y auditable.
# =============================================================================
set -e

echo "[entrypoint] Aplicando migraciones de base de datos..."
alembic upgrade head

echo "[entrypoint] Iniciando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
