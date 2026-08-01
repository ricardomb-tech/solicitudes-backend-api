"""
Configuración del consumidor (REQ-C: timeout y máximo de reintentos
configurables).

Mismo criterio que en el backend (ver backend/app/core/config.py): validación
de tipos al arranque con `pydantic-settings`, en lugar de leer `os.environ`
directamente.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # validation_alias explícito: backend y consumer comparten el mismo
    # archivo .env (ver .env.example), que define APP_NAME pensado para el
    # backend ("solicitudes-api"). Sin este alias, pydantic-settings mapearía
    # ese mismo APP_NAME aquí también (por convención de nombre de campo →
    # nombre de variable), y los logs del consumidor se identificarían
    # incorrectamente como "solicitudes-api" — un bug real detectado al
    # verificar la ejecución conjunta (ver bitácora, Bloque 5). Se usa una
    # variable con nombre propio, ausente en .env.example, así que el default
    # de abajo siempre se aplica.
    app_name: str = Field(default="solicitudes-consumer", validation_alias="CONSUMER_APP_NAME")
    log_level: str = "INFO"
    log_dir: str = "/app/logs"

    # URL base de la API a consumir. Tiene default porque coincide con el
    # nombre del servicio "backend" en docker-compose.yml (resuelto por el
    # DNS interno de Compose); se sobreescribe con la variable de entorno si
    # se necesita apuntar a otro destino (p. ej. en las pruebas).
    api_base_url: str = "http://backend:8000"

    # Tamaño del lote de solicitudes que se envía en cada ejecución.
    consumer_num_requests: int = 10

    # Timeouts separados por fase de la conexión HTTP (ver ADR-0013): un
    # timeout de conexión corto detecta rápido que el servidor no responde en
    # absoluto; un timeout de lectura más permisivo tolera que el servidor
    # esté simplemente ocupado procesando.
    consumer_timeout_connect_s: float = 3.0
    consumer_timeout_read_s: float = 10.0

    # Número de REINTENTOS (no de intentos totales): con el valor por defecto
    # de 3, una petición hace como máximo 1 intento inicial + 3 reintentos = 4
    # intentos totales antes de darse por vencida.
    consumer_max_retries: int = 3

    # Base del backoff exponencial con jitter, en segundos (ver ADR-0013).
    consumer_backoff_base_s: float = 0.5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
