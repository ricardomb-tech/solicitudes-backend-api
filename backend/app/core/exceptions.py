"""
Excepciones de dominio.

Estas excepciones describen situaciones del NEGOCIO, no de HTTP: "esta solicitud
ya existe", "no se puede pasar de completada a recibida". Deliberadamente no
heredan de `HTTPException` ni conocen códigos de estado.

Razón (ver ADR-0001): la capa de servicios no debe importar `fastapi`. Si las
reglas de negocio lanzaran `HTTPException`, quedarían atadas al transporte HTTP
y no podrían reutilizarse desde un consumidor de mensajería, un job programado o
una prueba unitaria sin arrastrar el framework web.

La traducción de excepción de dominio a código HTTP ocurre en un único lugar
(`app/core/error_handlers.py`), que es lo que el enunciado pide como "manejo
centralizado de excepciones".
"""
from typing import Any


class ErrorDominio(Exception):
    """
    Base de todas las excepciones de negocio.

    `codigo` es un identificador estable y legible por máquina (p. ej.
    `solicitud_duplicada`). Se expone al cliente para que pueda ramificar su
    lógica sin depender del texto del mensaje, que puede cambiar o traducirse.
    """

    codigo: str = "error_dominio"
    mensaje: str = "Ocurrió un error de negocio."

    def __init__(
        self, mensaje: str | None = None, detalles: list[dict[str, Any]] | None = None
    ) -> None:
        self.mensaje = mensaje or self.mensaje
        self.detalles = detalles or []
        super().__init__(self.mensaje)


class SolicitudDuplicada(ErrorDominio):
    """Ya existe una solicitud con el mismo identificador externo."""

    codigo = "solicitud_duplicada"
    mensaje = "Ya existe una solicitud registrada con ese identificador externo."

    def __init__(self, identificador_externo: str) -> None:
        super().__init__(
            detalles=[
                {
                    "campo": "identificador_externo",
                    "valor": identificador_externo,
                    "mensaje": "Este identificador ya fue registrado.",
                }
            ]
        )


class SolicitudNoEncontrada(ErrorDominio):
    """No existe una solicitud con el identificador consultado."""

    codigo = "solicitud_no_encontrada"
    mensaje = "No se encontró la solicitud indicada."


class TransicionEstadoInvalida(ErrorDominio):
    """
    El cambio de estado solicitado no está permitido por la máquina de estados.

    El detalle incluye los estados a los que SÍ se puede transicionar: un error
    que solo dice "no puedes" obliga al cliente a adivinar; uno que dice "no
    puedes, pero estas son tus opciones" es accionable.
    """

    codigo = "transicion_estado_invalida"
    mensaje = "El cambio de estado solicitado no está permitido."

    def __init__(
        self,
        estado_actual: str,
        estado_solicitado: str,
        estados_permitidos: list[str],
    ) -> None:
        if estados_permitidos:
            mensaje = (
                f"No se puede pasar de '{estado_actual}' a '{estado_solicitado}'. "
                f"Transiciones permitidas: {', '.join(sorted(estados_permitidos))}."
            )
        else:
            mensaje = (
                f"La solicitud está en estado '{estado_actual}', que es un estado "
                f"final y no admite cambios posteriores."
            )
        super().__init__(
            mensaje=mensaje,
            detalles=[
                {
                    "campo": "estado",
                    "estado_actual": estado_actual,
                    "estado_solicitado": estado_solicitado,
                    "estados_permitidos": sorted(estados_permitidos),
                }
            ],
        )
