"""
Capa de servicios: reglas de negocio de Solicitud.

Esta capa no importa `fastapi` ni conoce códigos HTTP (ver ADR-0001). Recibe y
devuelve objetos de dominio, y expresa los fallos como excepciones de dominio.
Podría reutilizarse desde un consumidor de mensajería o un job programado sin
arrastrar el framework web.
"""
import uuid

import structlog
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    SolicitudDuplicada,
    SolicitudNoEncontrada,
    TransicionEstadoInvalida,
)
from app.domain.enums import (
    EstadoSolicitud,
    Prioridad,
    TipoSolicitud,
    estados_alcanzables,
    transicion_es_valida,
)
from app.models.solicitud import Solicitud
from app.repositories.solicitud import SolicitudRepository
from app.schemas.solicitud import SolicitudCrear

logger = structlog.get_logger(__name__)


class SolicitudService:
    """
    --- Por qué el servicio recibe el repositorio Y la sesión ---

    El repositorio traduce objetos a SQL. La TRANSACCIÓN, en cambio, es una
    decisión de negocio: define qué conjunto de operaciones debe confirmarse o
    deshacerse como una unidad indivisible. Esa decisión pertenece al servicio,
    no al repositorio.

    Hoy cada caso de uso es una sola escritura, así que la diferencia parece
    académica. Deja de serlo en cuanto un caso de uso deba, por ejemplo, crear
    la solicitud y registrar un evento de auditoría de forma atómica: el
    servicio confirma una vez, al final, y ambas operaciones se aplican o
    ninguna. Si cada método del repositorio hiciera su propio `commit`, esa
    atomicidad sería imposible sin reescribir la capa de datos.

    Recibir el repositorio inyectado (en lugar de construirlo internamente)
    permite además sustituirlo por un doble de prueba y testear las reglas de
    negocio sin base de datos.
    """

    def __init__(self, repositorio: SolicitudRepository, session: Session) -> None:
        self._repositorio = repositorio
        self._session = session

    # ------------------------------------------------------------------ #
    def crear(self, datos: SolicitudCrear) -> Solicitud:
        """
        Registra una nueva solicitud.

        El estado inicial lo fija el sistema (no viaja en el esquema de
        entrada) y las fechas las genera el motor de base de datos.

        Si el identificador externo ya existe, el repositorio devuelve `None`
        —resultado normal de la operación atómica `ON CONFLICT`, no una
        excepción— y aquí se traduce a una excepción de dominio, que el
        manejador centralizado convertirá en `409 Conflict`.
        """
        solicitud = self._repositorio.crear_si_no_existe(datos.model_dump())

        if solicitud is None:
            # No es un error del sistema: es un resultado de negocio esperado
            # cuando dos peticiones compiten por el mismo identificador.
            raise SolicitudDuplicada(datos.identificador_externo)

        self._session.commit()
        logger.info(
            "solicitud_creada",
            solicitud_id=str(solicitud.id),
            identificador_externo=solicitud.identificador_externo,
        )
        return solicitud

    # ------------------------------------------------------------------ #
    def obtener(self, solicitud_id: uuid.UUID) -> Solicitud:
        solicitud = self._repositorio.obtener_por_id(solicitud_id)
        if solicitud is None:
            raise SolicitudNoEncontrada(
                f"No existe una solicitud con identificador {solicitud_id}."
            )
        return solicitud

    # ------------------------------------------------------------------ #
    def listar(
        self,
        *,
        estado: EstadoSolicitud | None = None,
        tipo: TipoSolicitud | None = None,
        prioridad: Prioridad | None = None,
        identificador_externo: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Solicitud], int]:
        settings = get_settings()
        # El tope máximo lo impone el servidor, no el cliente: sin este límite
        # una petición con `?limit=1000000` podría agotar la memoria del proceso.
        limite_efectivo = min(
            limit if limit is not None else settings.default_page_size,
            settings.max_page_size,
        )
        return self._repositorio.listar(
            estado=estado,
            tipo=tipo,
            prioridad=prioridad,
            identificador_externo=identificador_externo,
            limit=limite_efectivo,
            offset=offset,
        )

    # ------------------------------------------------------------------ #
    def actualizar_estado(
        self, solicitud_id: uuid.UUID, nuevo_estado: EstadoSolicitud
    ) -> Solicitud:
        """
        Cambia el estado de una solicitud respetando la máquina de estados.

        Aquí es donde la máquina de estados definida en el dominio deja de ser
        documentación y pasa a ser una regla aplicada: sin esta validación
        sería posible mover una solicitud de `completada` de vuelta a
        `recibida`, una inconsistencia que el enunciado no prohíbe
        explícitamente pero que ningún sistema de gestión real debería permitir.
        """
        solicitud = self.obtener(solicitud_id)
        estado_actual = EstadoSolicitud(solicitud.estado)

        # Cambiar al mismo estado se considera una operación sin efecto y se
        # acepta (idempotencia): reintentar un PATCH que ya se aplicó —algo que
        # hará el consumidor con su política de reintentos— no debe fallar.
        if estado_actual == nuevo_estado:
            logger.info(
                "estado_sin_cambio",
                solicitud_id=str(solicitud.id),
                estado=estado_actual.value,
            )
            return solicitud

        if not transicion_es_valida(estado_actual, nuevo_estado):
            raise TransicionEstadoInvalida(
                estado_actual=estado_actual.value,
                estado_solicitado=nuevo_estado.value,
                estados_permitidos=[e.value for e in estados_alcanzables(estado_actual)],
            )

        self._repositorio.actualizar_estado(solicitud, nuevo_estado)
        self._session.commit()
        logger.info(
            "estado_actualizado",
            solicitud_id=str(solicitud.id),
            estado_anterior=estado_actual.value,
            estado_nuevo=nuevo_estado.value,
        )
        return solicitud
