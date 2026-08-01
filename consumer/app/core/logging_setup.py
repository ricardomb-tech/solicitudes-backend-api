"""
Logging estructurado JSON del consumidor.

Este archivo es intencionalmente muy similar a `backend/app/core/logging.py`.
No se extrajo a un paquete compartido entre ambos servicios: ver la
justificación de "por qué NO compartir código entre servicios independientes"
en el README/ADR de este bloque. La duplicación aquí es small y deliberada,
no un descuido.
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog

from app.core.config import get_settings


def _agregar_servicio(_logger: Any, _metodo: str, evento: dict[str, Any]) -> dict[str, Any]:
    evento["service"] = get_settings().app_name
    return evento


def configurar_logging() -> None:
    settings = get_settings()
    nivel = getattr(logging, settings.log_level.upper(), logging.INFO)

    procesadores_comunes: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _agregar_servicio,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    formateador = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(ensure_ascii=False),
        foreign_pre_chain=procesadores_comunes,
    )

    manejadores: list[logging.Handler] = []

    manejador_stdout = logging.StreamHandler(sys.stdout)
    manejador_stdout.setFormatter(formateador)
    manejadores.append(manejador_stdout)

    try:
        directorio = Path(settings.log_dir)
        directorio.mkdir(parents=True, exist_ok=True)
        manejador_archivo = logging.handlers.RotatingFileHandler(
            directorio / "consumer.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        manejador_archivo.setFormatter(formateador)
        manejadores.append(manejador_archivo)
    except OSError:
        logging.getLogger(__name__).warning(
            "No se pudo habilitar el log en archivo; se usa solo stdout."
        )

    raiz = logging.getLogger()
    raiz.handlers = manejadores
    raiz.setLevel(nivel)

    structlog.configure(
        processors=[
            *procesadores_comunes,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
