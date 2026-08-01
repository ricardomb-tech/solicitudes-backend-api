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
# cada réplica — de lo contrario N réplicas intentarían migrar en paralelo. A
# diferencia de lo que una versión anterior de este comentario afirmaba,
# Alembic NO toma ningún bloqueo por sí solo: el bloqueo de fila sobre
# "alembic_version" ocurre en el UPDATE final, DESPUÉS del DDL, así que dos
# réplicas migrando a la vez sí pueden chocar (una falla con "ya existe" al
# hacer commit la otra). Por eso `migrations/env.py` toma explícitamente un
# advisory lock de PostgreSQL antes de aplicar cualquier migración: con él,
# la segunda réplica espera en vez de fallar. Aun así, separar el paso sigue
# siendo lo correcto para un despliegue real: más explícito, más auditable, y
# sin acoplar el arranque de cada réplica a permisos de escritura DDL sobre
# la base de datos.
# =============================================================================
set -e

echo "[entrypoint] Aplicando migraciones de base de datos..."
alembic upgrade head

echo "[entrypoint] Iniciando servidor..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
