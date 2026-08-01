"""
Clase base declarativa de SQLAlchemy.

Se define en su propio módulo (separado de `session.py`) para evitar
importaciones circulares: los modelos importan `Base` desde aquí, y Alembic
importa tanto `Base` como los modelos para poder detectar el esquema al
autogenerar migraciones. Si `Base` viviera junto al motor y la sesión, importar
un modelo arrastraría la creación del engine como efecto secundario.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa común a todos los modelos ORM del proyecto."""
