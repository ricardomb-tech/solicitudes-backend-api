"""
Endpoints de gestión de solicitudes — la capa más externa del sistema.

En la arquitectura de cuatro capas (ADR-0001), el router es deliberadamente
delgado: su único trabajo es traducir una petición HTTP en una llamada al
servicio, y el resultado del servicio en una respuesta HTTP. No contiene reglas
de negocio, no importa `sqlalchemy` y no sabe cómo se almacenan las
solicitudes.

La prueba mecánica de que la separación es real: este archivo no contiene ningún
`import sqlalchemy` ni `import psycopg`. Si alguien lo añadiera, la capa de
negocio y la de acceso a datos habrían colisionado en el endpoint — exactamente
lo que ADR-0001 existe para prevenir.

Nótese también que no hay ni un solo `try/except` aquí. Las excepciones de
dominio (solicitud duplicada, transición inválida, solicitud no encontrada)
suben libremente hasta los manejadores centralizados de
`app/core/error_handlers.py`, que deciden el código HTTP correspondiente.
Capturar las excepciones en cada endpoint repetiría la misma decisión en cada
archivo de router — y si el criterio de qué código corresponde a qué excepción
cambiara, habría que buscarlo y cambiarlo en todos lados.
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
    # 201 Created y no 200 OK: comunica que se originó un recurso nuevo, no que
    # se procesó una operación genérica. Es el código semánticamente correcto
    # para un POST que crea una entidad, y el que los clientes y los libros de
    # estilo REST esperan en este contexto.
    status_code=status.HTTP_201_CREATED,
    summary="Crear una solicitud",
    responses={
        409: {"description": "Ya existe una solicitud con ese identificador externo."},
        422: {"description": "Datos inválidos (campos faltantes, formato incorrecto o valor fuera de catálogo)."},
    },
)
def crear_solicitud(
    datos: SolicitudCrear, servicio: ServicioSolicitud
) -> SolicitudRespuesta:
    """
    Registra una nueva solicitud institucional en el sistema.

    Tres cosas que el cliente NO puede controlar y el sistema impone:
    - **Estado inicial**: toda solicitud nace en `recibida`, sin importar qué
      valor envíe el cliente (de hecho, el campo `estado` no existe en el cuerpo
      aceptado — ver `SolicitudCrear`). Si el cliente pudiera elegirlo, podría
      crear una solicitud ya marcada como `completada`, saltándose todo el flujo.
    - **Fechas**: `fecha_creacion` y `fecha_actualizacion` las genera la base de
      datos con `now()`. No se aceptan en el cuerpo.
    - **ID interno**: el UUID lo genera PostgreSQL con `gen_random_uuid()`. El
      cliente no lo envía; lo recibe en la respuesta.

    La unicidad de `identificador_externo` se garantiza de forma atómica en la
    base de datos (ADR-0003): dos peticiones simultáneas con el mismo
    identificador producen exactamente un `201 Created` y un `409 Conflict`,
    nunca dos creaciones ni un error inesperado.
    """
    solicitud = servicio.crear(datos)
    # `model_validate` construye el esquema de respuesta a partir del objeto
    # ORM directamente, sin convertirlo a diccionario a mano. Funciona porque
    # `SolicitudRespuesta` declara `from_attributes=True` en su configuración.
    return SolicitudRespuesta.model_validate(solicitud)


@router.get(
    "",
    response_model=SolicitudPagina,
    summary="Consultar solicitudes con filtros y paginación",
)
def listar_solicitudes(
    servicio: ServicioSolicitud,
    # Los filtros usan los Enum del dominio en lugar de `str` para dos motivos:
    # 1. FastAPI valida el valor antes de llegar al servicio — un `?estado=inventado`
    #    recibe un 422 sin tocar la base de datos ni escribir una validación manual.
    # 2. Los valores admitidos se publican automáticamente en la documentación
    #    OpenAPI, sin documentarlos a mano.
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
    # `le=100_000` en offset: sin esta cota (detectado en auditoría), un cliente
    # podía enviar `?offset=999999999` y obligar a PostgreSQL a recorrer y
    # descartar casi un millón de filas antes de entregar el resultado. Es
    # barato de enviar para el cliente y potencialmente costoso para la base de
    # datos. El mismo principio de "poner límites en todos los parámetros
    # numéricos del cliente" que ya aplicaba a `limit`.
    offset: int = Query(
        default=0, ge=0, le=100_000, description="Registros a omitir."
    ),
) -> SolicitudPagina:
    """
    Devuelve las solicitudes que cumplen los filtros, ordenadas de más reciente
    a más antigua (el índice `ix_solicitudes_fecha_creacion_desc` del modelo
    permite ese orden sin ordenamiento adicional en memoria).

    Los filtros son combinables: `?estado=recibida&prioridad=alta` aplica ambos.
    Sin filtros, devuelve todas las solicitudes paginadas.

    La respuesta es un objeto `SolicitudPagina` con `total`, `limit`, `offset`
    e `items`, no una lista desnuda. Eso permite al cliente construir una
    paginación y deja espacio para agregar campos en el futuro sin romper el
    contrato (una lista JSON en la raíz de la respuesta no es extensible sin un
    cambio incompatible para todos los clientes existentes).
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
    # `uuid.UUID` en lugar de `str`: FastAPI valida el formato del identificador
    # antes de ejecutar el handler. Un `GET /solicitudes/no-es-un-uuid` devuelve
    # 422 sin llegar a consultar la base de datos — ni siquiera se abre una
    # conexión. Si fuera `str`, esa validación habría que escribirla a mano o
    # dejar que PostgreSQL fallara con un error de tipo (que se traduciría en
    # un 500, no en un 422 descriptivo).
    solicitud_id: uuid.UUID = Path(description="Identificador interno (UUID)."),
) -> SolicitudRespuesta:
    """
    Devuelve los datos completos de una solicitud dado su UUID interno.

    `{solicitud_id}` es el `id` que el sistema asignó al crear la solicitud
    (ver ADR-0002), no el `identificador_externo` del sistema de origen. Para
    buscar por ese código se usa `GET /solicitudes?identificador_externo=...`.

    Si no existe ninguna solicitud con ese UUID, se responde `404 Not Found`.
    """
    solicitud = servicio.obtener(solicitud_id)
    return SolicitudRespuesta.model_validate(solicitud)


@router.patch(
    "/{solicitud_id}/estado",
    response_model=SolicitudRespuesta,
    summary="Actualizar el estado de una solicitud",
    responses={
        404: {"description": "La solicitud no existe."},
        409: {"description": "La transición de estado no está permitida desde el estado actual."},
    },
)
def actualizar_estado(
    datos: EstadoActualizar,
    servicio: ServicioSolicitud,
    solicitud_id: uuid.UUID = Path(description="Identificador interno (UUID)."),
) -> SolicitudRespuesta:
    """
    Avanza el estado de una solicitud siguiendo la máquina de estados del dominio
    (ADR-0017):

    ```
    recibida   →  en_proceso | rechazada
    en_proceso →  completada | rechazada
    completada →  (estado terminal, no acepta cambios)
    rechazada  →  (estado terminal, no acepta cambios)
    ```

    Una transición fuera del mapa devuelve `409 Conflict` indicando a qué
    estados sí se puede ir desde el estado actual — no solo "no puedes", sino
    "esto es lo que puedes hacer".

    **Idempotencia:** reenviar el estado que la solicitud ya tiene se acepta
    sin cambios (`200 OK`). Esto protege al consumidor (ADR-0013) en el
    escenario de reintento: si envió un `PATCH`, la respuesta se perdió por red
    y lo volvió a intentar, el segundo intento no debe fallar con `409` si el
    primero ya fue exitoso. Sin esta garantía, un reintento correcto produciría
    un error que no le correspondería.

    **PATCH y no PUT:** se modifica un único atributo del recurso (`estado`),
    no se reemplaza la solicitud completa. PUT semánticamente reemplaza la
    representación entera, lo que implicaría enviar todos los campos aunque no
    cambien — innecesario y propenso a sobreescrituras accidentales.
    """
    solicitud = servicio.actualizar_estado(solicitud_id, datos.estado)
    return SolicitudRespuesta.model_validate(solicitud)
