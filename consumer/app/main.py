"""
Punto de entrada del servicio consumidor: simula un sistema externo que
integra con la API de Solicitudes (REQ-C).

Flujo:
1. Espera activamente a que la API esté lista (defensa en profundidad: el
   healthcheck de Docker Compose ya lo garantiza, ver ADR-0014, pero un
   proceso robusto no debe depender de un único mecanismo externo).
2. Envía un lote de solicitudes (incluyendo un duplicado deliberado, ver
   generador_datos.py) y registra el resultado de cada una.
3. Consulta el estado de cada solicitud creada exitosamente.
4. Registra un resumen final.

Continúa su ejecución cuando una solicitud individual falla (REQ-C-07): un
fallo de negocio (409, 422) o incluso un agotamiento de reintentos en una
solicitud puntual no interrumpe el procesamiento de las demás. Solo se
retorna un código de salida distinto de 0 si el proceso mismo no pudo operar
en absoluto (la API nunca estuvo disponible).
"""
from __future__ import annotations

import sys
import time

import httpx
import structlog

from app.cliente_solicitudes import ejecutar_con_reintentos
from app.core.config import get_settings
from app.core.logging_setup import configurar_logging
from app.generador_datos import generar_lote

logger = structlog.get_logger(__name__)


def esperar_api_lista(
    cliente: httpx.Client, intentos: int = 30, espera_s: float = 2.0
) -> bool:
    for intento in range(1, intentos + 1):
        try:
            respuesta = cliente.get("/health/ready")
            if respuesta.status_code == 200:
                logger.info("api_lista", intento=intento)
                return True
            logger.info(
                "api_aun_no_lista", intento=intento, status=respuesta.status_code
            )
        except httpx.TransportError as exc:
            logger.info(
                "api_no_alcanzable", intento=intento, error_tipo=type(exc).__name__
            )
        time.sleep(espera_s)
    return False


def main() -> int:
    configurar_logging()
    settings = get_settings()

    logger.info(
        "consumidor_iniciado",
        api_base_url=settings.api_base_url,
        num_solicitudes=settings.consumer_num_requests,
        max_reintentos=settings.consumer_max_retries,
        timeout_conexion_s=settings.consumer_timeout_connect_s,
        timeout_lectura_s=settings.consumer_timeout_read_s,
    )

    # Timeouts separados por fase (ver ADR-0013 / config.py): un timeout de
    # conexión corto detecta rápido que el servidor no responde; el de
    # lectura tolera más tiempo de procesamiento del lado del servidor.
    timeout = httpx.Timeout(
        connect=settings.consumer_timeout_connect_s,
        read=settings.consumer_timeout_read_s,
        write=settings.consumer_timeout_read_s,
        pool=settings.consumer_timeout_read_s,
    )

    with httpx.Client(base_url=settings.api_base_url, timeout=timeout) as cliente:
        if not esperar_api_lista(cliente):
            logger.error("api_no_disponible_tras_espera")
            return 1

        lote = generar_lote(settings.consumer_num_requests)
        logger.info("lote_generado", cantidad=len(lote))

        creadas: list[dict] = []
        exitosas = 0
        fallidas_definitivas = 0
        fallidas_transitorias = 0
        intentos_totales = 0

        for payload in lote:
            resultado = ejecutar_con_reintentos(cliente, "POST", "/solicitudes", json=payload)
            intentos_totales += resultado.intentos_realizados

            if resultado.exito and resultado.respuesta is not None:
                exitosas += 1
                creadas.append(resultado.respuesta.json())
            elif resultado.es_fallo_definitivo:
                fallidas_definitivas += 1
            else:
                fallidas_transitorias += 1
            # REQ-C-07: continuar con la siguiente solicitud del lote pase lo
            # que pase con esta — no hay "raise" ni "return" anticipado aquí.

        logger.info(
            "fase_creacion_completada",
            exitosas=exitosas,
            fallidas_definitivas=fallidas_definitivas,
            fallidas_transitorias=fallidas_transitorias,
        )

        consultas_confirmadas = 0
        for solicitud in creadas:
            resultado = ejecutar_con_reintentos(
                cliente, "GET", f"/solicitudes/{solicitud['id']}"
            )
            if resultado.exito and resultado.respuesta is not None:
                consultas_confirmadas += 1
                logger.info(
                    "estado_confirmado",
                    solicitud_id=solicitud["id"],
                    identificador_externo=solicitud["identificador_externo"],
                    estado=resultado.respuesta.json()["estado"],
                )

        logger.info(
            "resumen_ejecucion",
            total_generadas=len(lote),
            creadas_exitosas=exitosas,
            fallidas_definitivas=fallidas_definitivas,
            fallidas_transitorias=fallidas_transitorias,
            consultas_confirmadas=consultas_confirmadas,
            intentos_http_totales=intentos_totales,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
