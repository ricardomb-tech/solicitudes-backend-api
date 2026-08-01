"""
Catálogos del dominio y reglas de transición de estado.

Este módulo es la ÚNICA fuente de verdad de los valores permitidos. Los
esquemas Pydantic (validación de entrada), el modelo SQLAlchemy (restricciones
`CHECK` en la base de datos) y la lógica de negocio importan desde aquí — nunca
se repite una lista de valores literal en otro archivo.

Consecuencia práctica: agregar un nuevo tipo de solicitud o una nueva prioridad
es un cambio en un solo lugar + una migración de Alembic, no una búsqueda de
cadenas repetidas por todo el proyecto.

Se hereda de `str` además de `Enum` (`class X(str, Enum)`) para que los valores
sean directamente serializables a JSON y comparables con cadenas, sin
conversiones manuales en los bordes de la aplicación.
"""
from enum import Enum


class TipoSolicitud(str, Enum):
    """Categoría de la solicitud (catálogo cerrado del enunciado)."""

    ACCESO_PLATAFORMA = "acceso_plataforma"
    SOPORTE_TECNICO = "soporte_tecnico"
    ACADEMICA = "academica"
    ADMINISTRATIVA = "administrativa"


class Prioridad(str, Enum):
    """Nivel de atención requerido."""

    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


class EstadoSolicitud(str, Enum):
    """Etapa actual de procesamiento."""

    RECIBIDA = "recibida"
    EN_PROCESO = "en_proceso"
    COMPLETADA = "completada"
    RECHAZADA = "rechazada"


#: Estado con el que nace toda solicitud. El cliente NO puede elegirlo al
#: crear: el estado inicial es responsabilidad del sistema, no de quien
#: registra la solicitud (de lo contrario alguien podría crear una solicitud
#: ya marcada como "completada", saltándose todo el flujo de atención).
ESTADO_INICIAL = EstadoSolicitud.RECIBIDA

#: Máquina de estados: por cada estado, el conjunto de estados a los que se
#: permite transicionar. Los estados terminales mapean a un conjunto vacío.
#:
#: Justificación (ver también docs/ARQUITECTURA.md): el enunciado pide
#: "actualizar el estado" sin especificar restricciones, pero permitir
#: transiciones arbitrarias haría válido pasar de "completada" de vuelta a
#: "recibida", una inconsistencia de negocio evidente. Modelar la máquina de
#: estados explícitamente convierte esa regla en algo verificable por un test,
#: en vez de una convención implícita que nadie garantiza.
TRANSICIONES_PERMITIDAS: dict[EstadoSolicitud, frozenset[EstadoSolicitud]] = {
    EstadoSolicitud.RECIBIDA: frozenset(
        {EstadoSolicitud.EN_PROCESO, EstadoSolicitud.RECHAZADA}
    ),
    EstadoSolicitud.EN_PROCESO: frozenset(
        {EstadoSolicitud.COMPLETADA, EstadoSolicitud.RECHAZADA}
    ),
    # Estados terminales: no admiten ninguna transición posterior.
    EstadoSolicitud.COMPLETADA: frozenset(),
    EstadoSolicitud.RECHAZADA: frozenset(),
}


def transicion_es_valida(
    estado_actual: EstadoSolicitud, estado_nuevo: EstadoSolicitud
) -> bool:
    """Indica si se permite pasar de `estado_actual` a `estado_nuevo`."""
    return estado_nuevo in TRANSICIONES_PERMITIDAS[estado_actual]


def estados_alcanzables(estado_actual: EstadoSolicitud) -> frozenset[EstadoSolicitud]:
    """
    Estados a los que se puede transicionar desde `estado_actual`.

    Se expone para que el mensaje de error de una transición inválida pueda
    decirle al cliente qué SÍ puede hacer, en lugar de solo rechazarlo.
    """
    return TRANSICIONES_PERMITIDAS[estado_actual]
