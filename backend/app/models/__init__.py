"""Modelos ORM. Se importan aquí para que Alembic los descubra al autogenerar."""
from app.models.solicitud import Solicitud

__all__ = ["Solicitud"]
