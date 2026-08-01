"""
Pruebas de la política de reintentos (REQ-C-04 a REQ-C-06).

Cada test construye un "guion" de respuestas: una lista de lo que el servidor
simulado debe responder en la 1ra, 2da, 3ra... llamada, y verifica tanto el
resultado final como el NÚMERO exacto de intentos que se realizaron —lo cual
es la única forma real de comprobar "si reintentó" o "si NO reintentó".
"""
from collections.abc import Callable

import httpx
import pytest

from app.cliente_solicitudes import ejecutar_con_reintentos


def _servidor_con_guion(respuestas: list[httpx.Response | Exception]):
    """
    Devuelve una función de manejador que entrega, en orden, cada elemento de
    `respuestas` en llamadas sucesivas. Si el elemento es una excepción, la
    lanza (simula un error de conexión); si es una Response, la devuelve.
    """
    llamadas = {"contador": 0}

    def manejador(_request: httpx.Request) -> httpx.Response:
        indice = llamadas["contador"]
        llamadas["contador"] += 1
        elemento = respuestas[indice]
        if isinstance(elemento, Exception):
            raise elemento
        return elemento

    manejador.llamadas = llamadas  # type: ignore[attr-defined]
    return manejador


def test_peticion_exitosa_al_primer_intento_no_reintenta(
    cliente_con_transporte_simulado: Callable,
) -> None:
    manejador = _servidor_con_guion([httpx.Response(201, json={"id": "abc"})])
    cliente = cliente_con_transporte_simulado(manejador)

    resultado = ejecutar_con_reintentos(cliente, "POST", "/solicitudes", json={})

    assert resultado.exito is True
    assert resultado.intentos_realizados == 1


@pytest.mark.parametrize("codigo_definitivo", [400, 404, 409, 422])
def test_error_4xx_definitivo_no_se_reintenta(
    cliente_con_transporte_simulado: Callable, codigo_definitivo: int
) -> None:
    """
    El punto central del requisito: "no reintentar errores definitivos, como
    respuestas 4xx". Se verifica con el número EXACTO de intentos (1, no más),
    no solo con que la petición "falló" — una prueba que solo mirara el
    resultado final no distinguiría "falló al primer intento" de "falló
    después de reintentar innecesariamente".
    """
    # Si el manejador fuera llamado una segunda vez, devolvería 201 —lo cual
    # haría fallar la aserción de "1 solo intento" en vez de esconder el bug.
    manejador = _servidor_con_guion(
        [httpx.Response(codigo_definitivo, json={"tipo": "error"}), httpx.Response(201)]
    )
    cliente = cliente_con_transporte_simulado(manejador)

    resultado = ejecutar_con_reintentos(cliente, "POST", "/solicitudes", json={})

    assert resultado.exito is False
    assert resultado.intentos_realizados == 1
    assert resultado.es_fallo_definitivo is True


@pytest.mark.parametrize("codigo_transitorio", [500, 502, 503, 504])
def test_error_5xx_transitorio_se_reintenta_hasta_tener_exito(
    cliente_con_transporte_simulado: Callable, codigo_transitorio: int
) -> None:
    manejador = _servidor_con_guion(
        [
            httpx.Response(codigo_transitorio),
            httpx.Response(codigo_transitorio),
            httpx.Response(201, json={"id": "abc"}),
        ]
    )
    cliente = cliente_con_transporte_simulado(manejador)

    resultado = ejecutar_con_reintentos(cliente, "POST", "/solicitudes", json={})

    assert resultado.exito is True
    assert resultado.intentos_realizados == 3


def test_error_de_conexion_se_reintenta(
    cliente_con_transporte_simulado: Callable,
) -> None:
    manejador = _servidor_con_guion(
        [httpx.ConnectError("conexión rechazada"), httpx.Response(201, json={"id": "x"})]
    )
    cliente = cliente_con_transporte_simulado(manejador)

    resultado = ejecutar_con_reintentos(cliente, "POST", "/solicitudes", json={})

    assert resultado.exito is True
    assert resultado.intentos_realizados == 2


def test_agota_reintentos_y_reporta_fallo_no_definitivo(
    cliente_con_transporte_simulado: Callable,
) -> None:
    """
    Con CONSUMER_MAX_RETRIES=3 (default), el máximo de intentos totales es 4
    (1 inicial + 3 reintentos). Si el servidor SIEMPRE responde 503, el
    consumidor debe rendirse tras exactamente 4 intentos, no colgarse
    indefinidamente, y clasificar el fallo como transitorio (no definitivo) —
    porque el problema nunca estuvo en la petición.
    """
    manejador = _servidor_con_guion([httpx.Response(503) for _ in range(10)])
    cliente = cliente_con_transporte_simulado(manejador)

    resultado = ejecutar_con_reintentos(cliente, "POST", "/solicitudes", json={})

    assert resultado.exito is False
    assert resultado.intentos_realizados == 4
    assert resultado.es_fallo_definitivo is False


def test_respeta_retry_after_en_respuesta_429(
    cliente_con_transporte_simulado: Callable, monkeypatch: pytest.MonkeyPatch
) -> None:
    esperas_registradas: list[float] = []
    monkeypatch.setattr(
        "app.cliente_solicitudes.time.sleep",
        lambda segundos: esperas_registradas.append(segundos),
    )

    manejador = _servidor_con_guion(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(201, json={"id": "x"}),
        ]
    )
    cliente = cliente_con_transporte_simulado(manejador)

    resultado = ejecutar_con_reintentos(cliente, "POST", "/solicitudes", json={})

    assert resultado.exito is True
    assert esperas_registradas == [7.0]


def test_correlation_id_es_el_mismo_en_todos_los_intentos(
    cliente_con_transporte_simulado: Callable,
) -> None:
    """
    El identificador de correlación debe viajar idéntico en cada reintento de
    la misma operación lógica: es lo que permite, en los logs reales,
    agrupar los N intentos de una misma petición bajo un solo identificador.
    """
    correlation_ids_recibidos: list[str | None] = []

    def manejador(request: httpx.Request) -> httpx.Response:
        correlation_ids_recibidos.append(request.headers.get("X-Correlation-ID"))
        if len(correlation_ids_recibidos) < 3:
            return httpx.Response(503)
        return httpx.Response(201, json={"id": "x"})

    cliente = cliente_con_transporte_simulado(manejador)

    ejecutar_con_reintentos(cliente, "POST", "/solicitudes", json={})

    assert len(correlation_ids_recibidos) == 3
    assert len(set(correlation_ids_recibidos)) == 1
    assert correlation_ids_recibidos[0] is not None
