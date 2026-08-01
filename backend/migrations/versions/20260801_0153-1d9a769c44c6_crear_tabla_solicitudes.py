"""crear tabla solicitudes

Revision ID: 1d9a769c44c6
Revises:
Create Date: 2026-08-01 01:53:06.871739

Migración inicial del esquema. Generada con `alembic revision --autogenerate`
y revisada manualmente antes de aceptarse: el autogenerado es un punto de
partida, no un resultado final — omite regularmente índices por expresión,
detalles de tipos y datos de respaldo, así que aceptarlo sin leerlo es una
fuente conocida de migraciones incorrectas.

Puntos verificados manualmente en esta revisión:
- La restricción UNIQUE sobre `identificador_externo` está presente: es el
  invariante del que depende el manejo de concurrencia con `ON CONFLICT`
  (ver ADR-0003). Sin ella, `ON CONFLICT (identificador_externo)` fallaría en
  tiempo de ejecución por falta de un índice único al que asociar el conflicto.
- Los `CHECK` de catálogo se generaron a partir de los Enum del dominio.
- El índice por expresión `fecha_creacion DESC` se generó correctamente (es el
  caso que el autogenerado suele omitir; aquí se declaró con `sa.text(...)` en
  el modelo, por lo que sí quedó incluido).
- `downgrade()` revierte el cambio por completo (índices y tabla), de modo que
  la migración es reversible.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "1d9a769c44c6"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "solicitudes",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("identificador_externo", sa.String(length=64), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("nombre_solicitante", sa.String(length=150), nullable=False),
        sa.Column("correo", sa.String(length=254), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("prioridad", sa.String(length=10), nullable=False),
        sa.Column(
            "estado",
            sa.String(length=15),
            server_default=sa.text("'recibida'"),
            nullable=False,
        ),
        sa.Column(
            "fecha_creacion",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "fecha_actualizacion",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('recibida', 'en_proceso', 'completada', 'rechazada')",
            name="ck_solicitudes_estado",
        ),
        sa.CheckConstraint(
            "prioridad IN ('baja', 'media', 'alta')",
            name="ck_solicitudes_prioridad",
        ),
        sa.CheckConstraint(
            "tipo IN ('acceso_plataforma', 'soporte_tecnico', 'academica', "
            "'administrativa')",
            name="ck_solicitudes_tipo",
        ),
        sa.PrimaryKeyConstraint("id"),
        # UNIQUE sobre el identificador del sistema de origen. En PostgreSQL
        # una restricción UNIQUE crea implícitamente un índice único, que es
        # justamente el índice al que `ON CONFLICT (identificador_externo)`
        # se asocia para resolver el conflicto de forma atómica.
        sa.UniqueConstraint("identificador_externo"),
    )
    # Índice compuesto para el filtro combinado del listado (estado/tipo/
    # prioridad). Sirve también a los prefijos (estado) y (estado, tipo).
    op.create_index(
        "ix_solicitudes_estado_tipo_prioridad",
        "solicitudes",
        ["estado", "tipo", "prioridad"],
        unique=False,
    )
    # Índice por expresión para el orden por defecto del listado.
    op.create_index(
        "ix_solicitudes_fecha_creacion_desc",
        "solicitudes",
        [sa.text("fecha_creacion DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_solicitudes_fecha_creacion_desc", table_name="solicitudes")
    op.drop_index("ix_solicitudes_estado_tipo_prioridad", table_name="solicitudes")
    op.drop_table("solicitudes")
