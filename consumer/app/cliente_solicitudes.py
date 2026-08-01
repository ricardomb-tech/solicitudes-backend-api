"""
Cliente HTTP hacia la API de Solicitudes, con la política de reintentos de
`app/retry.py` ya aplicada.
"""
from __future__ import annotations

import time
import uuid

import httpx
import structlog

from app.core.config import get_settings
from app.retry import (
    ResultadoPeticion,
    calcular_espera,
    es_respuesta_transitoria,
    segundos_de_retry_after,
)

logger = structlog.get_logger(__name__)

CABECERA_CORRELACION = "X-Correlation-ID"


def ejecutar_con_reintentos(
    cliente: httpx.Client,
    metodo: str,
    ruta: str,
    *,
    json: dict | None = None,
    correlation_id: str | None = None,
) -> ResultadoPeticion:
    """
    Ejecuta una petición HTTP aplicando la política de reintentos completa.

    El `correlation_id` se genera aquí, en el consumidor —el origen de la
    operación—, y se envía en la cabecera `X-Correlation-ID` en TODOS los
    intentos de la misma operación lógica (no uno nuevo por intento): así, en
    los logs, los N intentos de la misma petición lógica se agrupan bajo el
    mismo identificador, y el backend que la reciba propagará ese mismo valor
    (ver ADR-0009 del backend). Esto es lo que hace posible reconstruir el
    viaje completo de una operación a través de ambos servicios.
    """
    settings = get_settings()
    correlation_id = correlation_id or str(uuid.uuid4())
    max_intentos = settings.consumer_max_retries + 1  # 1 intento inicial + N reintentos

    for intento in range(1, max_intentos + 1):
        inicio = time.perf_counter()
        cabeceras = {CABECERA_CORRELACION: correlation_id}

        try:
            respuesta = cliente.request(metodo, ruta, json=json, headers=cabeceras)
        except httpx.TransportError as exc:
            # httpx.TransportError es la clase base de TODOS los errores de
            # transporte: ConnectError, TimeoutException, NetworkError, y
            # también ProtocolError/RemoteProtocolError ("Server disconnected
            # without sending a response") — este último ocurre cuando una
            # conexión keep-alive reutilizada del pool de httpx es cerrada por
            # el servidor justo antes de reutilizarse (Uvicorn cierra las
            # conexiones inactivas a los 5s por defecto; con reintentos
            # espaciados por el backoff de este mismo módulo, la ventana de
            # carrera es real). Antes se capturaba solo un subconjunto
            # (Connect/Timeout/Network), y ese error concreto escapaba sin
            # capturar hasta abortar el lote completo — justo lo que REQ-C-07
            # ("continuar su ejecución cuando una solicitud falle") prohíbe.
            #
            # Por definición, ningún error de transporte llegó a producir una
            # respuesta HTTP: son transitorios — el servidor pudo no estar
            # disponible en este instante exacto, pero la petición en sí no
            # tiene nada de inválido.
            duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)
            logger.warning(
                "error_de_conexion",
                method=metodo,
                path=ruta,
                intento=intento,
                max_intentos=max_intentos,
                duration_ms=duracion_ms,
                correlation_id=correlation_id,
                error_tipo=type(exc).__name__,
                error_detalle=str(exc),
            )
            if intento == max_intentos:
                logger.error(
                    "reintentos_agotados",
                    method=metodo,
                    path=ruta,
                    correlation_id=correlation_id,
                    motivo="error_de_conexion",
                )
                return ResultadoPeticion(
                    exito=False,
                    intentos_realizados=intento,
                    error=f"{type(exc).__name__}: {exc}",
                )
            time.sleep(calcular_espera(intento, settings.consumer_backoff_base_s))
            continue

        duracion_ms = round((time.perf_counter() - inicio) * 1000, 2)

        if respuesta.status_code < 400:
            logger.info(
                "peticion_exitosa",
                method=metodo,
                path=ruta,
                status=respuesta.status_code,
                intento=intento,
                duration_ms=duracion_ms,
                correlation_id=correlation_id,
            )
            return ResultadoPeticion(
                exito=True, intentos_realizados=intento, respuesta=respuesta
            )

        if not es_respuesta_transitoria(respuesta):
            # Error DEFINITIVO (4xx real, distinto de 429): no se reintenta.
            # Ejemplo: 409 por identificador duplicado, 422 por datos
            # inválidos. Reintentar la misma petición produciría el mismo
            # resultado exacto.
            logger.warning(
                "peticion_fallida_definitiva",
                method=metodo,
                path=ruta,
                status=respuesta.status_code,
                intento=intento,
                duration_ms=duracion_ms,
                correlation_id=correlation_id,
                detalle=_resumen_error(respuesta),
            )
            return ResultadoPeticion(
                exito=False, intentos_realizados=intento, respuesta=respuesta
            )

        # Error TRANSITORIO (5xx o 429).
        logger.warning(
            "peticion_fallida_transitoria",
            method=metodo,
            path=ruta,
            status=respuesta.status_code,
            intento=intento,
            max_intentos=max_intentos,
            duration_ms=duracion_ms,
            correlation_id=correlation_id,
        )

        if intento == max_intentos:
            logger.error(
                "reintentos_agotados",
                method=metodo,
                path=ruta,
                correlation_id=correlation_id,
                motivo=f"status_{respuesta.status_code}",
            )
            return ResultadoPeticion(
                exito=False, intentos_realizados=intento, respuesta=respuesta
            )

        espera = segundos_de_retry_after(respuesta)
        if espera is None:
            espera = calcular_espera(intento, settings.consumer_backoff_base_s)
        else:
            logger.info(
                "respetando_retry_after",
                segundos=espera,
                correlation_id=correlation_id,
            )
        time.sleep(espera)

    # Inalcanzable en la práctica (el bucle siempre retorna en la última
    # iteración), se deja como red de seguridad explícita en vez de dejar que
    # la función devuelva None implícitamente.
    return ResultadoPeticion(exito=False, intentos_realizados=max_intentos)


def _resumen_error(respuesta: httpx.Response) -> str:
    """
    Extrae solo el campo "titulo" del contrato de error del backend
    (ver ADR-0008), en vez de volcar el cuerpo completo al log: el consumidor
    no necesita, y no debería asumir, más estructura de la que el contrato
    público le garantiza.
    """
    try:
        return respuesta.json().get("titulo", respuesta.text[:200])
    except ValueError:
        return respuesta.text[:200]
