"""
Pruebas UNITARIAS de la máquina de estados, aisladas de PostgreSQL mediante
un doble de prueba del repositorio (sin `TestClient`, sin Docker, sin red).

ADR-0001 prometía que "los tests de `services/` corren sin base de datos real
usando dobles del repositorio" — una auditoría posterior encontró que esa
promesa no tenía ningún test real detrás: las 49 pruebas del backend pasaban,
sin excepción, por `TestClient` contra PostgreSQL real (ver
`tests/conftest.py`), incluso para probar reglas que viven enteramente en
Python (la máquina de estados de `app/domain/enums.py`). Este archivo cierra
esa brecha y demuestra el beneficio concreto de haber separado
`services/` de `repositories/` (ver ADR-0001): la regla de negocio más
elaborada del proyecto se verifica en milisegundos, sin infraestructura.

No sustituye a `tests/test_actualizar_estado.py` (que sigue siendo necesario
para probar la integración real: HTTP, serialización, persistencia). Ambos
prueban la misma regla desde ángulos distintos y complementarios.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app.core.exceptions import SolicitudNoEncontrada, TransicionEstadoInvalida
from app.domain.enums import EstadoSolicitud
from app.services.solicitud import SolicitudService


@dataclass
class _SolicitudFalsa:
    """
    Objeto mínimo con los únicos dos atributos que `SolicitudService` toca
    para esta operación (`id`, `estado`) — no es una instancia real del
    modelo ORM, ni falta que lo sea: el servicio no importa `sqlalchemy`
    (ver ADR-0001), así que no necesita saber la diferencia.
    """

    id: uuid.UUID
    estado: str


class _RepositorioFalso:
    """
    Doble de `SolicitudRepository`: mantiene las solicitudes en un
    diccionario en memoria. Implementa únicamente los dos métodos que
    `actualizar_estado` invoca — no reimplementa `crear_si_no_existe` ni
    `listar`, que no participan de esta regla de negocio.
    """

    def __init__(self, solicitudes: dict[uuid.UUID, _SolicitudFalsa]) -> None:
        self._solicitudes = solicitudes

    def obtener_por_id(self, solicitud_id: uuid.UUID) -> _SolicitudFalsa | None:
        return self._solicitudes.get(solicitud_id)

    def actualizar_estado(
        self, solicitud: _SolicitudFalsa, nuevo_estado: EstadoSolicitud
    ) -> _SolicitudFalsa:
        solicitud.estado = nuevo_estado.value
        return solicitud


class _SesionFalsa:
    """
    Doble de la sesión de SQLAlchemy: `actualizar_estado` llama a
    `self._session.commit()` al final. Aquí no hay nada que confirmar de
    verdad, así que basta con no fallar.
    """

    def commit(self) -> None:
        return None


@pytest.fixture
def solicitud_falsa() -> _SolicitudFalsa:
    return _SolicitudFalsa(id=uuid.uuid4(), estado=EstadoSolicitud.RECIBIDA.value)


@pytest.fixture
def servicio(solicitud_falsa: _SolicitudFalsa) -> SolicitudService:
    repositorio = _RepositorioFalso({solicitud_falsa.id: solicitud_falsa})
    return SolicitudService(repositorio, _SesionFalsa())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("estado_origen", "estado_destino"),
    [
        (EstadoSolicitud.RECIBIDA, EstadoSolicitud.EN_PROCESO),
        (EstadoSolicitud.RECIBIDA, EstadoSolicitud.RECHAZADA),
        (EstadoSolicitud.EN_PROCESO, EstadoSolicitud.COMPLETADA),
        (EstadoSolicitud.EN_PROCESO, EstadoSolicitud.RECHAZADA),
    ],
)
def test_transiciones_permitidas_sin_base_de_datos(
    servicio: SolicitudService,
    solicitud_falsa: _SolicitudFalsa,
    estado_origen: EstadoSolicitud,
    estado_destino: EstadoSolicitud,
) -> None:
    solicitud_falsa.estado = estado_origen.value

    resultado = servicio.actualizar_estado(solicitud_falsa.id, estado_destino)

    assert resultado.estado == estado_destino.value


@pytest.mark.parametrize(
    ("estado_origen", "estado_destino"),
    [
        (EstadoSolicitud.RECIBIDA, EstadoSolicitud.COMPLETADA),  # salta "en_proceso"
        (EstadoSolicitud.COMPLETADA, EstadoSolicitud.RECIBIDA),  # retrocede desde terminal
        (EstadoSolicitud.COMPLETADA, EstadoSolicitud.EN_PROCESO),
        (EstadoSolicitud.RECHAZADA, EstadoSolicitud.RECIBIDA),
        (EstadoSolicitud.RECHAZADA, EstadoSolicitud.EN_PROCESO),
    ],
)
def test_transiciones_no_permitidas_sin_base_de_datos(
    servicio: SolicitudService,
    solicitud_falsa: _SolicitudFalsa,
    estado_origen: EstadoSolicitud,
    estado_destino: EstadoSolicitud,
) -> None:
    solicitud_falsa.estado = estado_origen.value

    with pytest.raises(TransicionEstadoInvalida) as excinfo:
        servicio.actualizar_estado(solicitud_falsa.id, estado_destino)

    # El mensaje debe ser accionable: decir a qué estados sí se puede ir.
    assert excinfo.value.detalles[0]["estados_permitidos"] is not None


def test_reenviar_mismo_estado_es_idempotente_sin_base_de_datos(
    servicio: SolicitudService, solicitud_falsa: _SolicitudFalsa
) -> None:
    solicitud_falsa.estado = EstadoSolicitud.EN_PROCESO.value

    resultado = servicio.actualizar_estado(
        solicitud_falsa.id, EstadoSolicitud.EN_PROCESO
    )

    assert resultado.estado == EstadoSolicitud.EN_PROCESO.value


def test_solicitud_inexistente_sin_base_de_datos(servicio: SolicitudService) -> None:
    with pytest.raises(SolicitudNoEncontrada):
        servicio.actualizar_estado(uuid.uuid4(), EstadoSolicitud.EN_PROCESO)
