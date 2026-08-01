"""
Configuración de logging estructurado en formato JSON (REQ-L-*).

Dos decisiones de fondo:

1. **JSON, no texto plano.** Un log de texto se lee bien con los ojos y muy mal
   con una máquina: extraer "todas las peticiones que tardaron más de 500 ms"
   exige expresiones regulares frágiles. Con JSON, cada campo es consultable
   directamente (CloudWatch Logs Insights, Loki, Elasticsearch) sin parseo. El
   enunciado lo señala como valorado positivamente, y es además lo que hace
   viable la trazabilidad centralizada de la propuesta de AWS.

2. **Doble salida: stdout + archivo rotado.**
   - `stdout` es el contrato con el orquestador (principio 12-factor: la
     aplicación no gestiona archivos de log, los emite al flujo estándar). Es
     lo que consume `docker compose logs -f`, y en AWS lo que recoge el driver
     de logs de ECS hacia CloudWatch.
   - El archivo en volumen cumple el requisito literal de "persistencia de los
     logs" más allá del ciclo de vida del contenedor.

   Se usa `RotatingFileHandler` y no un archivo plano: sin rotación, un
   servicio de larga duración llena el disco. Es un fallo operativo clásico.

Se integra `structlog` con el `logging` estándar de la biblioteca en lugar de
usarlo por separado, para que los logs de Uvicorn y de SQLAlchemy —que usan
`logging` estándar— salgan también en JSON. Si no se hiciera, el flujo de salida
mezclaría líneas JSON con líneas de texto plano y ningún recolector podría
procesarlo de forma uniforme.
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog

from app.core.config import get_settings

_LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB por archivo
_LOG_FILE_BACKUPS = 5  # ~50 MB máximo en disco


def _agregar_servicio(
    _logger: Any, _metodo: str, evento: dict[str, Any]
) -> dict[str, Any]:
    """
    Inyecta el nombre del servicio en cada registro (REQ-L: "nombre del servicio").

    Es imprescindible cuando los logs de varios servicios se centralizan en un
    mismo destino: sin este campo no se puede saber quién emitió cada línea.
    """
    evento["service"] = get_settings().app_name
    return evento


def configurar_logging() -> None:
    settings = get_settings()
    nivel = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Procesadores aplicados a TODOS los registros, incluidos los que provienen
    # del logging estándar (Uvicorn, SQLAlchemy), no solo los de structlog.
    procesadores_comunes: list[Any] = [
        # merge_contextvars trae al registro las variables ligadas al contexto
        # de la petición actual (correlation_id, entre otras). Es lo que permite
        # que el correlation_id aparezca en CADA log de una petición sin tener
        # que pasarlo como parámetro por todas las capas de la aplicación.
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        _agregar_servicio,
        # Marca de tiempo ISO-8601 en UTC: formato no ambiguo y ordenable
        # lexicográficamente (una cadena ISO en UTC se ordena igual que el
        # instante que representa, lo que simplifica consultas y agregaciones).
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

    # La escritura a archivo se intenta, pero no es crítica: si el volumen no
    # está montado o no hay permisos de escritura, el servicio debe seguir
    # funcionando y logueando por stdout. Un fallo en la persistencia de logs
    # no debe tumbar la aplicación.
    try:
        directorio = Path(settings.log_dir)
        directorio.mkdir(parents=True, exist_ok=True)
        manejador_archivo = logging.handlers.RotatingFileHandler(
            directorio / "app.log",
            maxBytes=_LOG_FILE_MAX_BYTES,
            backupCount=_LOG_FILE_BACKUPS,
            encoding="utf-8",
        )
        manejador_archivo.setFormatter(formateador)
        manejadores.append(manejador_archivo)
    except OSError:
        # Se avisa por stdout, que sí está disponible, y se continúa.
        logging.getLogger(__name__).warning(
            "No se pudo habilitar el log en archivo; se usa solo stdout."
        )

    raiz = logging.getLogger()
    raiz.handlers = manejadores
    raiz.setLevel(nivel)

    # Uvicorn instala sus propios manejadores con formato de texto. Se vacían y
    # se les fuerza a propagar al logger raíz para que su salida también sea
    # JSON y no se dupliquen líneas.
    for nombre in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger_uvicorn = logging.getLogger(nombre)
        logger_uvicorn.handlers = []
        logger_uvicorn.propagate = True

    structlog.configure(
        processors=[
            *procesadores_comunes,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def obtener_logger(nombre: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(nombre)
