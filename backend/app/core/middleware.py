"""
Middleware de correlación y registro de peticiones.

Implementa el requisito de que cada registro de log incluya identificador de
correlación, método, endpoint, código de respuesta y tiempo de ejecución
(REQ-L-*), y sienta la base de la trazabilidad distribuida que la propuesta de
AWS describe.
"""
import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CABECERA_CORRELACION = "X-Correlation-ID"

logger = structlog.get_logger(__name__)


class MiddlewareCorrelacion(BaseHTTPMiddleware):
    """
    Asigna un identificador de correlación a cada petición y registra su
    resultado en una única línea estructurada.

    --- Por qué el identificador se PROPAGA en vez de generarse siempre ---

    Si la petición ya trae la cabecera `X-Correlation-ID`, se reutiliza; solo se
    genera uno nuevo cuando no viene. Esa distinción es la que hace posible
    seguir una operación a través de varios servicios: el consumidor genera el
    identificador, lo envía en la cabecera, esta API lo adopta, y ambos lados
    escriben logs con el MISMO valor. Buscar ese valor reconstruye el viaje
    completo de la operación.

    Si cada servicio generase su propio identificador, cada uno tendría su
    historia por separado y no habría forma de unirlas.

    --- Por qué contextvars ---

    `structlog.contextvars.bind_contextvars` liga el identificador al contexto
    de ejecución de esta petición. A partir de ahí, CUALQUIER log emitido
    durante la petición —desde el router, el servicio o el repositorio— lo
    incluye automáticamente, sin necesidad de pasarlo como parámetro por toda
    la cadena de llamadas. Al usar `contextvars` (y no una variable global), dos
    peticiones concurrentes no se pisan el valor entre sí.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = request.headers.get(CABECERA_CORRELACION) or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        # Se guarda también en el estado de la petición para que los manejadores
        # de excepciones puedan incluirlo en el cuerpo de la respuesta de error.
        request.state.correlation_id = correlation_id

        # perf_counter (reloj monótono), no time(): no se ve afectado por
        # ajustes del reloj del sistema (NTP), que podrían producir duraciones
        # negativas o incorrectas al medir intervalos.
        inicio = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)
            # exc_info=True incluye el traceback COMPLETO en el log —donde sí
            # debe estar—, mientras que la respuesta al cliente será genérica
            # (ver error_handlers.py). Esa asimetría es exactamente lo que pide
            # el requisito de "no exponer información técnica sensible".
            logger.error(
                "peticion_fallida",
                method=request.method,
                path=request.url.path,
                status=500,
                duration_ms=duracion_ms,
                exc_info=True,
            )
            raise

        duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)

        # Una única línea por petición, con todos los campos exigidos. Un log
        # por petición (y no varios) mantiene el volumen acotado y hace que
        # cada línea sea un registro completo y autosuficiente.
        logger.info(
            "peticion_completada",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duracion_ms,
        )

        # Devolver el identificador al cliente le permite citarlo al reportar un
        # problema, y al equipo de soporte encontrar la traza exacta.
        response.headers[CABECERA_CORRELACION] = correlation_id
        return response
