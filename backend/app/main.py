"""
Punto de entrada de la aplicación FastAPI.

Bloque 1 (fundación): solo se expone GET /health (liveness) — confirma que el
proceso de la API está vivo y puede responder peticiones HTTP, sin depender de
ningún recurso externo. Deliberadamente NO se agrega aquí /health/ready: ese
endpoint verifica la conexión a PostgreSQL y se implementa en el Bloque 3,
cuando exista una capa de datos real. Un "ready" que no verifica nada real
sería una falsa señal de salud, peor que no tenerlo.
"""
from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="API para gestión de solicitudes institucionales.",
    version="0.1.0",
)


@app.get(
    "/health",
    tags=["salud"],
    summary="Liveness: verifica que el proceso de la API está vivo",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
