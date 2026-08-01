"""
Configuración centralizada de la aplicación (REQ-T-03: configuración mediante
variables de entorno).

Se usa `pydantic-settings` en lugar de leer `os.environ` directamente por dos
razones concretas:

1. Valida tipos y presencia de variables obligatorias al arrancar el proceso
   ("fail fast"): si falta DATABASE_URL, la aplicación no arranca y lo dice
   con un mensaje claro, en vez de arrancar "bien" y fallar más tarde, en el
   primer intento de conexión, con un traceback menos informativo.
2. Actúa como documentación ejecutable de qué variables de entorno existen,
   sus tipos y sus valores por defecto, en un único lugar del código.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "solicitudes-api"
    app_env: str = "development"
    log_level: str = "INFO"

    # Directorio donde se persisten los logs en archivo (montado como volumen
    # en docker-compose.yml). La salida por stdout es independiente de esto.
    log_dir: str = "/app/logs"

    # Obligatoria: si no está definida, la app falla al arrancar (fail fast).
    database_url: str

    # Tope de resultados por página en el listado. Evita que un cliente pida
    # `?limit=1000000` y provoque una respuesta que agote la memoria del
    # proceso: el límite lo impone el servidor, no la confianza en el cliente.
    max_page_size: int = 100
    default_page_size: int = 50

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # El .env es compartido a nivel de proyecto (Postgres, consumer, etc.);
        # "ignore" evita que variables de otros servicios rompan la validación
        # de este servicio.
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cachea la instancia de Settings: las variables de entorno no cambian
    durante la vida del proceso, así que se parsean y validan una sola vez
    en el primer acceso, no en cada request.
    """
    return Settings()
