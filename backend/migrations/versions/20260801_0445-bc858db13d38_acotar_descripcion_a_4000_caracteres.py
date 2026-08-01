"""acotar descripcion a 4000 caracteres

Revision ID: bc858db13d38
Revises: 1d9a769c44c6
Create Date: 2026-08-01 04:45:07.764243

Segunda migración del proyecto (la primera, "crear tabla solicitudes",
nunca había necesitado una sucesora, así que este es también el primer
ejercicio real del flujo de "evolucionar el esquema" descrito en ADR-0004).

Motivo: `descripcion` era el único campo de texto del modelo sin longitud
máxima (columna `Text`), a diferencia de todos los demás
(`identificador_externo` 64, `nombre_solicitante` 150, `correo` 254). Un
cliente podía enviar una descripción de tamaño arbitrario, que Starlette
bufferiza completa en memoria antes de que Pydantic la rechace — un vector de
denegación de servicio por agotamiento de memoria, detectado en una auditoría
posterior a la entrega inicial. El límite de 4000 caracteres ya se aplicó en
el esquema Pydantic (`app/schemas/solicitud.py`); esta migración lo refleja
también en la base de datos, coherente con el resto del modelo.

Nota operativa (no aplica a este proyecto, pero es la razón de este
comentario): `ALTER COLUMN ... TYPE VARCHAR(n)` sobre una columna `TEXT`
obliga a PostgreSQL a verificar que **todas** las filas existentes ya cumplen
la nueva longitud, lo cual toma un `ACCESS EXCLUSIVE lock` sobre la tabla
durante el escaneo. Sobre una tabla pequeña (como la de esta prueba) es
instantáneo; sobre una tabla de producción con millones de filas, sería una
migración a programar en una ventana de mantenimiento, no a aplicar en caliente
en el arranque de cada réplica (ver la propia advertencia en
`backend/entrypoint.sh` sobre por qué las migraciones deberían ser un paso
separado del despliegue en un entorno real).
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "bc858db13d38"
down_revision: str | None = "1d9a769c44c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "solicitudes",
        "descripcion",
        existing_type=sa.TEXT(),
        type_=sa.String(length=4000),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "solicitudes",
        "descripcion",
        existing_type=sa.String(length=4000),
        type_=sa.TEXT(),
        existing_nullable=False,
    )
