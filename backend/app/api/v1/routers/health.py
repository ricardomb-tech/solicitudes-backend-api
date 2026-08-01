"""
Endpoints de salud.

--- Por qué son DOS endpoints y no uno (liveness vs. readiness) ---

Responden preguntas distintas y un orquestador reacciona distinto a cada una:

  GET /health        (liveness)  -> "¿el proceso está vivo?"
      NO consulta la base de datos. Si un chequeo de vida dependiera de
      PostgreSQL, una caída temporal de la base de datos haría que el
      orquestador (Docker, ECS, Kubernetes) considerara "muertos" a
      contenedores perfectamente sanos y los reiniciara en bucle — empeorando
      el incidente en lugar de mitigarlo.

  GET /health/ready  (readiness) -> "¿puedo atender tráfico ahora?"
      SÍ verifica PostgreSQL. Si la base de datos no responde, el servicio no
      puede cumplir su función aunque el proceso siga vivo. Un balanceador lo
      saca de rotación (deja de enviarle peticiones) pero NO lo mata, dándole
      oportunidad de recuperarse solo cuando la dependencia vuelva.

Esta distinción no es teórica: en la propuesta de AWS, el health check del
target group del ALB apunta a `/health/ready` precisamente por este motivo.
"""
from typing import Any

import structlog
from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import SesionBD
from app.core.config import get_settings

router = APIRouter(tags=["salud"])
logger = structlog.get_logger(__name__)


@router.get(
    "/health",
    summary="Liveness: verifica que el proceso de la API responde",
)
def health() -> dict[str, str]:
    """
    Chequeo de vida. Deliberadamente no consulta dependencias externas: debe
    responder afirmativamente mientras el proceso sea capaz de atender HTTP.
    """
    settings = get_settings()
    return {"status": "ok", "servicio": settings.app_name}


@router.get(
    "/health/ready",
    summary="Readiness: verifica la conexión con PostgreSQL",
    responses={
        200: {"description": "El servicio puede atender tráfico."},
        503: {"description": "Alguna dependencia no está disponible."},
    },
)
def health_ready(session: SesionBD, response: Response) -> dict[str, Any]:
    """
    Chequeo de disponibilidad: comprueba que la base de datos responde.

    Se ejecuta `SELECT 1`, la consulta más barata posible que aun así recorre
    el camino completo (pool de conexiones → red → servidor → respuesta). No se
    consulta ninguna tabla del negocio a propósito: el chequeo debe verificar
    conectividad, no depender de que exista determinado dato.

    Ante un fallo se devuelve `503 Service Unavailable` (el servicio existe
    pero no puede atender ahora), no `500`. El detalle técnico del fallo va al
    log, nunca al cuerpo de la respuesta.
    """
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.error("readiness_fallido", dependencia="postgresql", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "degraded",
            "dependencias": {"postgresql": "no_disponible"},
        }

    return {"status": "ok", "dependencias": {"postgresql": "disponible"}}
