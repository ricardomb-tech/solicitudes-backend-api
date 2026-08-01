"""
Endpoints de gestión de solicitudes.

Los routers son deliberadamente delgados: parsean la petición, delegan en el
servicio y serializan la respuesta. No contienen reglas de negocio ni acceso a
datos, y no importan `sqlalchemy` (ver ADR-0001).

Nótese que aquí no hay ni un solo `try/except`: las excepciones de dominio
suben libremente hasta los manejadores centralizados
(`app/core/error_handlers.py`), que las traducen a códigos HTTP. Capturarlas en
cada endpoint repetiría la misma decisión en muchos lugares y haría que un
cambio de criterio obligara a tocar todos los archivos.
"""
import uuid

from fastapi import APIRouter, Path, Query, status

from app.api.deps import ServicioSolicitud
from app.core.config import get_settings
from app.domain.enums import EstadoSolicitud, Prioridad, TipoSolicitud
from app.schemas.solicitud import (
    EstadoActualizar,
    SolicitudCrear,
    SolicitudPagina,
    SolicitudRespuesta,
)

router = APIRouter(prefix="/solicitudes", tags=["solicitudes"])

settings = get_settings()


@router.post(
    "",
    response_model=SolicitudRespuesta,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una solicitud",
    responses={
        409: {"description": "Ya existe una solicitud con ese identificador externo."},
        422: {"description": "Datos inválidos."},
    },
)
def crear_solicitud(
    datos: SolicitudCrear, servicio: ServicioSolicitud
) -> SolicitudRespuesta:
    """
    Registra una nueva solicitud institucional.

    - El **estado** inicial lo asigna el sistema (`recibida`); no se acepta en
      el cuerpo de la petición.
    - Las **fechas** las genera la base de datos.
    - El **identificador externo** debe ser único: si ya existe, se responde
      `409 Conflict`. Esta comprobación es atómica, por lo que dos peticiones
      simultáneas con el mismo identificador producen exactamente una creación
      y un conflicto, nunca un duplicado ni un error interno.
    """
    # 201 Created es el código correcto para una creación exitosa, no 200:
    # comunica que se originó un recurso nuevo.
    solicitud = servicio.crear(datos)
    return SolicitudRespuesta.model_validate(solicitud)


@router.get(
    "",
    response_model=SolicitudPagina,
    summary="Consultar solicitudes con filtros y paginación",
)
def listar_solicitudes(
    servicio: ServicioSolicitud,
    # Los filtros se declaran con los Enum del dominio: FastAPI valida el valor
    # ANTES de llegar al servicio y, además, publica los valores admitidos en
    # la documentación OpenAPI automáticamente. Un `?estado=inventado` se
    # rechaza con 422 sin tocar la base de datos.
    estado: EstadoSolicitud | None = Query(
        default=None, description="Filtrar por estado."
    ),
    tipo: TipoSolicitud | None = Query(
        default=None, description="Filtrar por tipo de solicitud."
    ),
    prioridad: Prioridad | None = Query(
        default=None, description="Filtrar por prioridad."
    ),
    identificador_externo: str | None = Query(
        default=None, description="Buscar por el código del sistema de origen."
    ),
    limit: int = Query(
        default=settings.default_page_size,
        ge=1,
        le=settings.max_page_size,
        description="Cantidad máxima de resultados por página.",
    ),
    # le=100_000: sin cota superior (encontrado en auditoría), un
    # "?offset=999999999" obliga a PostgreSQL a recorrer y descartar esa
    # cantidad de filas antes de responder — barato de pedir, caro de
    # ejecutar. El mismo criterio que ya se aplicaba a "limit".
    offset: int = Query(
        default=0, ge=0, le=100_000, description="Registros a omitir."
    ),
) -> SolicitudPagina:
    """
    Devuelve las solicitudes que cumplen los filtros, ordenadas de más reciente
    a más antigua.

    Los filtros son combinables: `?estado=recibida&prioridad=alta` aplica ambos.
    """
    items, total = servicio.listar(
        estado=estado,
        tipo=tipo,
        prioridad=prioridad,
        identificador_externo=identificador_externo,
        limit=limit,
        offset=offset,
    )
    return SolicitudPagina(
        total=total,
        limit=limit,
        offset=offset,
        items=[SolicitudRespuesta.model_validate(item) for item in items],
    )


@router.get(
    "/{solicitud_id}",
    response_model=SolicitudRespuesta,
    summary="Consultar una solicitud específica",
    responses={404: {"description": "La solicitud no existe."}},
)
def obtener_solicitud(
    servicio: ServicioSolicitud,
    # El tipo `uuid.UUID` hace que FastAPI valide el formato antes de ejecutar
    # el endpoint: un identificador mal formado devuelve 422 sin llegar a
    # consultar la base de datos.
    solicitud_id: uuid.UUID = Path(description="Identificador interno (UUID)."),
) -> SolicitudRespuesta:
    solicitud = servicio.obtener(solicitud_id)
    return SolicitudRespuesta.model_validate(solicitud)


@router.patch(
    "/{solicitud_id}/estado",
    response_model=SolicitudRespuesta,
    summary="Actualizar el estado de una solicitud",
    responses={
        404: {"description": "La solicitud no existe."},
        409: {"description": "La transición de estado no está permitida."},
    },
)
def actualizar_estado(
    datos: EstadoActualizar,
    servicio: ServicioSolicitud,
    solicitud_id: uuid.UUID = Path(description="Identificador interno (UUID)."),
) -> SolicitudRespuesta:
    """
    Cambia el estado siguiendo la máquina de estados del dominio:

    - `recibida` → `en_proceso` o `rechazada`
    - `en_proceso` → `completada` o `rechazada`
    - `completada` y `rechazada` son estados finales y no admiten cambios.

    Una transición no permitida devuelve `409 Conflict` indicando qué estados
    sí son alcanzables. Reenviar el estado que la solicitud ya tiene se acepta
    sin cambios (operación idempotente), de modo que un reintento del cliente
    no produce un error.

    Se usa **PATCH** y no PUT porque se modifica un único atributo del recurso,
    no se reemplaza el recurso completo.
    """
    solicitud = servicio.actualizar_estado(solicitud_id, datos.estado)
    return SolicitudRespuesta.model_validate(solicitud)
