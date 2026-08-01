"""
Fixtures compartidas de las pruebas del consumidor.

--- Por qué se usa httpx.MockTransport en vez de un backend real ---

Estas pruebas verifican la POLÍTICA DE REINTENTOS en sí misma: qué hace el
consumidor ante un 503, ante un error de conexión, ante un 429 con
Retry-After, ante un 404. Para probar eso de forma determinista hace falta
poder producir esas respuestas exactas, en el orden exacto, sin depender de
que un servidor real falle en el momento preciso que el test necesita —lo
cual sería no determinista e imposible de reproducir de forma fiable.

`httpx.MockTransport` reemplaza la capa de transporte de red del cliente
httpx por una función de Python controlada por el test, sin abrir ningún
socket real. Es el mismo principio que se aplicó en las pruebas del backend
(`backend/tests/test_health.py`, `test_errores.py`) para simular una base de
datos caída (un doble de prueba en el punto exacto de la dependencia
externa), aplicado aquí al cliente HTTP saliente en lugar de a la sesión de
base de datos.
"""
from collections.abc import Callable

import httpx
import pytest


@pytest.fixture(autouse=True)
def _sin_esperas_reales(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Reemplaza `time.sleep` por un no-op en el módulo bajo prueba.

    La política de reintentos usa backoff exponencial real (hasta varios
    segundos). Sin este fixture, la suite de pruebas tardaría minutos en
    verificar escenarios de "se agotaron los reintentos". El COMPORTAMIENTO
    de reintentar (cuántas veces, con qué criterio) es lo que se verifica;
    CUÁNTO tiempo se espera entre reintentos ya se prueba por separado y de
    forma aislada en test_calcular_espera.
    """
    monkeypatch.setattr("app.cliente_solicitudes.time.sleep", lambda _segundos: None)


@pytest.fixture
def cliente_con_transporte_simulado() -> Callable[[Callable], httpx.Client]:
    """
    Fábrica de clientes httpx cuyo transporte real se sustituye por una
    función controlada por el test (`manejador`), que recibe cada
    `httpx.Request` y decide qué `httpx.Response` devolver.
    """

    def _crear(manejador: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
        transporte = httpx.MockTransport(manejador)
        return httpx.Client(base_url="http://api-simulada.test", transport=transporte)

    return _crear
