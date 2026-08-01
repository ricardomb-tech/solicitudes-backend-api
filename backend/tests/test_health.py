"""
Pruebas de los endpoints de salud (REQ-F: GET /health, GET /health/ready).

Ver ADR-0010 para la justificación de por qué son dos endpoints distintos.
"""
from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db


def test_liveness_responde_200_sin_depender_de_la_base_de_datos(
    client: TestClient,
) -> None:
    respuesta = client.get("/health")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "ok"
    assert "servicio" in cuerpo


def test_readiness_responde_200_cuando_la_base_de_datos_esta_disponible(
    client: TestClient,
) -> None:
    respuesta = client.get("/health/ready")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "ok"
    assert cuerpo["dependencias"]["postgresql"] == "disponible"


class _SesionQueFalla:
    """
    Doble de prueba que simula una sesión de base de datos incapaz de
    responder — reproduce, sin necesidad de detener el contenedor real de
    PostgreSQL, el mismo escenario descrito en ADR-0010.
    """

    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise OperationalError(
            "SELECT 1", {}, Exception("conexión con la base de datos perdida")
        )


def test_readiness_responde_503_cuando_la_base_de_datos_no_responde(
    app_instance: FastAPI, client: TestClient
) -> None:
    """
    Formaliza como test automatizado la verificación manual descrita en
    ADR-0010: deteniendo PostgreSQL, `/health/ready` respondía 503 mientras
    `/health` seguía en 200. Aquí se simula el fallo sustituyendo la
    dependencia en vez de detener el contenedor real, para que la prueba sea
    determinista y no afecte a las demás pruebas de la sesión.
    """

    def _override_fallido() -> Iterator[_SesionQueFalla]:
        yield _SesionQueFalla()

    app_instance.dependency_overrides[get_db] = _override_fallido

    respuesta = client.get("/health/ready")

    assert respuesta.status_code == 503
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "degraded"
    assert cuerpo["dependencias"]["postgresql"] == "no_disponible"


def test_liveness_sigue_en_200_aunque_la_base_de_datos_no_responda(
    app_instance: FastAPI, client: TestClient
) -> None:
    """
    El punto central de ADR-0010: un fallo de la dependencia NO debe hacer
    que el chequeo de vida falle, o el orquestador reiniciaría en bucle un
    proceso que en realidad está sano.
    """

    def _override_fallido() -> Iterator[_SesionQueFalla]:
        yield _SesionQueFalla()

    app_instance.dependency_overrides[get_db] = _override_fallido

    respuesta = client.get("/health")

    assert respuesta.status_code == 200
