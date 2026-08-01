"""
Punto de entrada de la aplicación FastAPI.

Se usa una función factoría (`crear_app`) en lugar de construir la aplicación
directamente a nivel de módulo. Motivo: permite crear instancias independientes
en las pruebas (cada una con su propia configuración y sus propias
dependencias sustituidas) sin arrastrar estado compartido entre tests.
"""
from fastapi import FastAPI

from app.api.v1.routers import health, solicitudes
from app.core.config import get_settings
from app.core.error_handlers import registrar_manejadores
from app.core.logging import configurar_logging
from app.core.middleware import MiddlewareCorrelacion

DESCRIPCION = """
API para la gestión de solicitudes institucionales.

Permite registrar solicitudes provenientes de sistemas externos, consultarlas
con filtros y hacer seguimiento de su estado a lo largo del flujo de atención.

### Contrato de errores

Todos los errores comparten la misma estructura, sin importar su origen:

```json
{
  "tipo": "solicitud_duplicada",
  "titulo": "Ya existe una solicitud registrada con ese identificador externo.",
  "estado": 409,
  "correlation_id": "3f2b8c14-...",
  "detalles": [ ... ]
}
```

El campo `correlation_id` identifica la petición en los logs del servidor:
cítelo al reportar un problema. También se devuelve en la cabecera
`X-Correlation-ID` de toda respuesta, y si el cliente la envía en la petición,
el servicio la reutiliza para permitir trazabilidad entre sistemas.
"""


def crear_app() -> FastAPI:
    # El logging se configura ANTES de instanciar la aplicación, para que los
    # mensajes emitidos durante el arranque ya salgan en formato JSON.
    configurar_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPCION,
        version="1.0.0",
        # Documentación automática OpenAPI/Swagger (REQ-T-04).
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # El middleware se registra antes que los routers para que envuelva a todas
    # las peticiones, incluidas las que terminan en error.
    app.add_middleware(MiddlewareCorrelacion)

    # Manejo centralizado de excepciones (REQ-T-02).
    registrar_manejadores(app)

    app.include_router(health.router)
    app.include_router(solicitudes.router)

    return app


app = crear_app()
