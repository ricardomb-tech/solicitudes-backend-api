"""
Dependencias compartidas de la API.

Centralizar aquí el "cableado" (qué repositorio y qué sesión recibe cada
servicio) mantiene a los routers libres de detalles de construcción: un router
declara que necesita un `SolicitudService` y no sabe nada sobre sesiones ni
repositorios. Cambiar la implementación del repositorio no obliga a tocar
ningún endpoint.

Es además el punto donde FastAPI permite sustituir dependencias en las pruebas
(`app.dependency_overrides`), lo que hará posible testear los endpoints
inyectando dobles sin levantar infraestructura real.
"""
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.solicitud import SolicitudRepository
from app.services.solicitud import SolicitudService

SesionBD = Annotated[Session, Depends(get_db)]


def obtener_servicio_solicitud(session: SesionBD) -> SolicitudService:
    return SolicitudService(SolicitudRepository(session), session)


ServicioSolicitud = Annotated[SolicitudService, Depends(obtener_servicio_solicitud)]
