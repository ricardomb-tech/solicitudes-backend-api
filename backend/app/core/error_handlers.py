"""
Manejo centralizado de excepciones (REQ-T-02) y contrato uniforme de errores.

Todo error que salga de esta API —de validación, de negocio o inesperado—
tiene la MISMA forma. Un cliente puede escribir una sola rutina de manejo de
errores en lugar de una por endpoint.

Formato de respuesta (inspirado en RFC 9457 "Problem Details for HTTP APIs",
adaptado al español del dominio):

    {
      "tipo": "solicitud_duplicada",
      "titulo": "Ya existe una solicitud registrada con ese identificador externo.",
      "estado": 409,
      "correlation_id": "3f2b...",
      "detalles": [ {...} ]
    }

- `tipo`: identificador estable, legible por máquina. El cliente ramifica por
  este campo, no por el texto (que puede cambiar o traducirse).
- `correlation_id`: permite unir la respuesta que vio el cliente con la traza
  completa en los logs del servidor. Es la pieza que hace compatible "no
  exponer detalles técnicos" con "poder diagnosticar el problema".
"""
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    ErrorDominio,
    SolicitudDuplicada,
    SolicitudNoEncontrada,
    TransicionEstadoInvalida,
)

logger = structlog.get_logger(__name__)

# Traducción de excepción de dominio a código HTTP. Este diccionario es el
# ÚNICO lugar del proyecto donde se decide qué código corresponde a qué
# situación de negocio: ni los servicios ni los routers repiten esa decisión.
#
# Justificación de cada código:
#   409 Conflict  -> la petición es válida, pero choca con el estado actual del
#                    servidor. Aplica tanto al duplicado (ya existe ese
#                    identificador) como a la transición inválida (el estado
#                    actual no admite ese cambio). No es 400: la petición está
#                    bien formada. No es 422: los valores son semánticamente
#                    válidos, el conflicto es con el estado, no con el dato.
#   404 Not Found -> el recurso solicitado no existe.
MAPA_HTTP: dict[type[ErrorDominio], int] = {
    SolicitudDuplicada: status.HTTP_409_CONFLICT,
    SolicitudNoEncontrada: status.HTTP_404_NOT_FOUND,
    TransicionEstadoInvalida: status.HTTP_409_CONFLICT,
}


def _obtener_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "no-disponible")


def _respuesta_error(
    *,
    codigo_http: int,
    tipo: str,
    titulo: str,
    correlation_id: str,
    detalles: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    cuerpo: dict[str, Any] = {
        "tipo": tipo,
        "titulo": titulo,
        "estado": codigo_http,
        "correlation_id": correlation_id,
    }
    if detalles:
        cuerpo["detalles"] = detalles
    return JSONResponse(status_code=codigo_http, content=cuerpo)


def registrar_manejadores(app: FastAPI) -> None:
    """Registra todos los manejadores de excepciones en la aplicación."""

    @app.exception_handler(ErrorDominio)
    async def manejar_error_dominio(
        request: Request, exc: ErrorDominio
    ) -> JSONResponse:
        codigo_http = MAPA_HTTP.get(type(exc), status.HTTP_400_BAD_REQUEST)
        correlation_id = _obtener_correlation_id(request)

        # Nivel WARNING, no ERROR: un duplicado o una transición inválida son
        # resultados ESPERADOS del negocio, no fallos del sistema. Clasificarlos
        # como ERROR contaminaría las alertas y haría que el equipo dejara de
        # prestarles atención (fatiga de alertas).
        logger.warning(
            "error_dominio",
            tipo=exc.codigo,
            status=codigo_http,
            mensaje=exc.mensaje,
        )
        return _respuesta_error(
            codigo_http=codigo_http,
            tipo=exc.codigo,
            titulo=exc.mensaje,
            correlation_id=correlation_id,
            detalles=exc.detalles,
        )

    @app.exception_handler(RequestValidationError)
    async def manejar_error_validacion(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Errores de validación de Pydantic.

        Se conserva el código 422 (el estándar de FastAPI) en lugar de
        convertirlo a 400: el cuerpo está bien formado sintácticamente pero es
        semánticamente inválido, que es justo lo que significa 422. Cambiarlo
        rompería la coherencia con el resto del ecosistema FastAPI y con la
        documentación OpenAPI que se genera automáticamente.

        Lo que SÍ se cambia es el formato del cuerpo, para que un error de
        validación tenga la misma forma que cualquier otro error de la API.
        """
        detalles = [
            {
                # `loc` incluye el origen ("body", "query") como primer elemento;
                # se omite para dejar solo la ruta al campo problemático.
                "campo": ".".join(str(parte) for parte in error["loc"][1:]) or "cuerpo",
                "mensaje": error["msg"],
                "tipo_error": error["type"],
            }
            for error in exc.errors()
        ]
        correlation_id = _obtener_correlation_id(request)
        logger.warning("error_validacion", status=422, cantidad_errores=len(detalles))
        return _respuesta_error(
            codigo_http=status.HTTP_422_UNPROCESSABLE_ENTITY,
            tipo="error_validacion",
            titulo="Los datos enviados no son válidos.",
            correlation_id=correlation_id,
            detalles=detalles,
        )

    @app.exception_handler(StarletteHTTPException)
    async def manejar_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """
        Excepciones HTTP de Starlette/FastAPI (404 de ruta inexistente, 405 de
        método no permitido, etc.).

        Se re-formatean al mismo contrato para que ni siquiera un 404 de ruta
        equivocada devuelva una forma distinta al resto de errores.
        """
        correlation_id = _obtener_correlation_id(request)
        return _respuesta_error(
            codigo_http=exc.status_code,
            tipo="error_http",
            titulo=str(exc.detail),
            correlation_id=correlation_id,
        )

    @app.exception_handler(Exception)
    async def manejar_error_no_controlado(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Red de seguridad para cualquier excepción no prevista (REQ-V-06).

        Aquí está el punto crítico de seguridad de todo el manejo de errores:

        - AL LOG va todo: tipo de excepción, mensaje y traceback completo
          (`exc_info=True`), porque es información interna y necesaria para
          diagnosticar.
        - AL CLIENTE va un mensaje genérico y el `correlation_id`, nada más.

        Devolver `str(exc)` al cliente —el atajo habitual— filtra rutas de
        archivos, nombres de tablas y columnas, fragmentos de SQL y, en el peor
        caso, credenciales incluidas en una cadena de conexión. Ese es
        exactamente el tipo de fuga que el enunciado pide evitar.

        El `correlation_id` cierra el círculo: el cliente reporta ese valor y el
        equipo encuentra la traza exacta en los logs, sin haber expuesto nada.
        """
        correlation_id = _obtener_correlation_id(request)
        logger.error(
            "error_no_controlado",
            tipo_excepcion=type(exc).__name__,
            status=500,
            exc_info=True,
        )
        return _respuesta_error(
            codigo_http=status.HTTP_500_INTERNAL_SERVER_ERROR,
            tipo="error_interno",
            titulo=(
                "Ocurrió un error interno procesando la solicitud. "
                "Cite el identificador de correlación al reportar el problema."
            ),
            correlation_id=correlation_id,
        )
