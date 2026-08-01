"""
Capa de acceso a datos para Solicitud.

Es la ÚNICA capa del proyecto que conoce SQLAlchemy (ver ADR-0001). Los
servicios reciben y devuelven objetos de dominio; no saben si detrás hay
PostgreSQL, otro motor o una API remota.
"""
import uuid
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.enums import EstadoSolicitud, Prioridad, TipoSolicitud
from app.models.solicitud import Solicitud


class SolicitudRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ #
    # Escritura
    # ------------------------------------------------------------------ #
    def crear_si_no_existe(self, datos: dict[str, Any]) -> Solicitud | None:
        """
        Inserta una solicitud de forma ATÓMICA respecto al identificador externo.

        Devuelve la solicitud creada, o `None` si ya existía una con el mismo
        `identificador_externo` (es decir, si otra transacción ganó la carrera).

        --- Por qué está escrito así (ver ADR-0003) ---

        La forma intuitiva de evitar duplicados sería:

            if repo.obtener_por_identificador_externo(x):   # (1) comprobar
                raise Duplicado()
            repo.insertar(...)                              # (2) insertar

        Ese código tiene una condición de carrera conocida como TOCTOU
        (time-of-check to time-of-use): entre (1) y (2) hay una ventana en la
        que otra transacción concurrente puede insertar el mismo identificador.
        Ambas peticiones leen "no existe", ambas intentan insertar, y el
        resultado es un error de integridad no controlado (HTTP 500) — o, si no
        hubiera restricción UNIQUE en la base de datos, un duplicado real.

        La solución es no comprobar antes: se delega la decisión al motor, que
        evalúa el conflicto y escribe en una sola operación indivisible.
        `ON CONFLICT DO NOTHING` con `RETURNING` devuelve la fila si la
        inserción ocurrió, y ninguna fila si el identificador ya existía. Un
        solo viaje a la base de datos, sin bloqueos manuales y sin depender de
        capturar una excepción como flujo de control normal.
        """
        sentencia = (
            pg_insert(Solicitud)
            .values(**datos)
            .on_conflict_do_nothing(index_elements=["identificador_externo"])
            .returning(Solicitud)
        )
        return self._session.execute(sentencia).scalar_one_or_none()

    def actualizar_estado(
        self, solicitud: Solicitud, nuevo_estado: EstadoSolicitud
    ) -> Solicitud:
        """
        Actualiza el estado de una solicitud ya cargada.

        `fecha_actualizacion` no se toca aquí: la refresca automáticamente el
        `onupdate=func.now()` del modelo, evaluado por el motor. Escribirla a
        mano desde Python reintroduciría el problema de relojes desincronizados
        que el diseño del modelo evita deliberadamente.
        """
        solicitud.estado = nuevo_estado.value
        self._session.flush()
        return solicitud

    # ------------------------------------------------------------------ #
    # Lectura
    # ------------------------------------------------------------------ #
    def obtener_por_id(self, solicitud_id: uuid.UUID) -> Solicitud | None:
        return self._session.get(Solicitud, solicitud_id)

    def obtener_por_identificador_externo(
        self, identificador_externo: str
    ) -> Solicitud | None:
        sentencia = select(Solicitud).where(
            Solicitud.identificador_externo == identificador_externo
        )
        return self._session.execute(sentencia).scalar_one_or_none()

    def listar(
        self,
        *,
        estado: EstadoSolicitud | None = None,
        tipo: TipoSolicitud | None = None,
        prioridad: Prioridad | None = None,
        identificador_externo: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Solicitud], int]:
        """
        Lista solicitudes aplicando filtros opcionales y paginación.

        Devuelve `(items, total)`, donde `total` es la cantidad de registros que
        cumplen el filtro ignorando la paginación — el cliente lo necesita para
        saber cuántas páginas hay.

        Se ejecutan dos consultas (una de conteo y una de datos) en lugar de
        usar una ventana `COUNT(*) OVER ()`: el plan resultante es más simple y
        el conteo puede aprovechar el índice sin traer las filas completas.
        """
        filtros = self._construir_filtros(
            estado=estado,
            tipo=tipo,
            prioridad=prioridad,
            identificador_externo=identificador_externo,
        )

        consulta_total: Select[tuple[int]] = select(func.count()).select_from(Solicitud)
        for filtro in filtros:
            consulta_total = consulta_total.where(filtro)
        total = self._session.execute(consulta_total).scalar_one()

        consulta = select(Solicitud)
        for filtro in filtros:
            consulta = consulta.where(filtro)
        # Orden estable y determinista: más recientes primero. Sin un ORDER BY
        # explícito, PostgreSQL no garantiza ningún orden entre páginas, y la
        # paginación produciría resultados repetidos u omitidos.
        consulta = (
            consulta.order_by(Solicitud.fecha_creacion.desc(), Solicitud.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self._session.execute(consulta).scalars().all())

        return items, total

    @staticmethod
    def _construir_filtros(
        *,
        estado: EstadoSolicitud | None,
        tipo: TipoSolicitud | None,
        prioridad: Prioridad | None,
        identificador_externo: str | None,
    ) -> list[Any]:
        """
        Traduce filtros opcionales a condiciones SQL.

        Se construyen con la API de expresiones de SQLAlchemy, nunca
        concatenando cadenas SQL: los valores viajan como parámetros
        vinculados, lo que elimina por construcción el riesgo de inyección SQL.
        """
        filtros: list[Any] = []
        if estado is not None:
            filtros.append(Solicitud.estado == estado.value)
        if tipo is not None:
            filtros.append(Solicitud.tipo == tipo.value)
        if prioridad is not None:
            filtros.append(Solicitud.prioridad == prioridad.value)
        if identificador_externo is not None:
            filtros.append(Solicitud.identificador_externo == identificador_externo)
        return filtros
