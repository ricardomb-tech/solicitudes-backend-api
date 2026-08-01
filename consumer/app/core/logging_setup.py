"""
Logging estructurado JSON del consumidor.

Este archivo es intencionalmente muy similar a `backend/app/core/logging.py`.
No se extrajo a un paquete compartido entre ambos servicios (ver ADR-0016,
que además señala explícitamente que la justificación de "independencia entre
servicios" aplica con más fuerza a dominio de negocio con contrato HTTP de
por medio —como los catálogos— que a infraestructura interna sin ningún
contrato que la desacople, como este archivo). La duplicación aquí es
pequeña y deliberada, no un descuido, pero se acepta con ese matiz: si la
política de rotación de logs cambiara, hay que recordar tocar los dos
archivos, y nada lo verifica automáticamente.
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog

from app.core.config import get_settings

# Mismos valores que backend/app/core/logging.py (10 MB x 5 archivos). Se
# nombran aquí también, en vez de dejarlos como literales inline, para que
# comparar ambos archivos y detectar una futura divergencia sea trivial.
_LOG_FILE_MAX_BYTES = 10 * 1024 * 1024
_LOG_FILE_BACKUPS = 5


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
            maxBytes=_LOG_FILE_MAX_BYTES,
            backupCount=_LOG_FILE_BACKUPS,
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
