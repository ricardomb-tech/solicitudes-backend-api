"""
Pruebas del manejo centralizado de errores (REQ-V-06: no exponer información
técnica sensible en los errores). Formaliza la verificación manual del
Bloque 3 (detener PostgreSQL y observar la respuesta).
"""
from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.session import get_db


class _SesionQueFallaConDetalleTecnico:
    """
    Simula una excepción de infraestructura real, con un mensaje que
    deliberadamente incluye el tipo de dato que NUNCA debe llegar al cliente:
    fragmento de SQL, nombre de host y usuario de la base de datos.
    """

    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError(
            "connection to server at host=db user=solicitudes_user "
            'failed: FATAL: password authentication failed; '
            "query: SELECT * FROM solicitudes WHERE estado = 'recibida'"
        )


def test_error_no_controlado_devuelve_mensaje_generico_con_correlation_id(
    app_instance: FastAPI, client: TestClient
) -> None:
    def _override_fallido() -> Iterator[_SesionQueFallaConDetalleTecnico]:
        yield _SesionQueFallaConDetalleTecnico()

    app_instance.dependency_overrides[get_db] = _override_fallido

    respuesta = client.get("/solicitudes")

    assert respuesta.status_code == 500
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "error_interno"
    assert "correlation_id" in cuerpo
    assert cuerpo["correlation_id"] != ""


def test_error_no_controlado_no_filtra_ningun_detalle_tecnico(
    app_instance: FastAPI, client: TestClient
) -> None:
    """
    Verificación explícita, palabra por palabra, de que ninguno de los
    fragmentos sensibles del error original aparece en la respuesta HTTP —
    el punto exacto que el enunciado exige ("evitar la exposición de
    información técnica sensible en los errores").
    """

    def _override_fallido() -> Iterator[_SesionQueFallaConDetalleTecnico]:
        yield _SesionQueFallaConDetalleTecnico()

    app_instance.dependency_overrides[get_db] = _override_fallido

    respuesta = client.get("/solicitudes")
    texto_completo_de_la_respuesta = respuesta.text

    fragmentos_prohibidos = [
        "solicitudes_user",
        "host=db",
        "password authentication failed",
        "SELECT * FROM solicitudes",
        "RuntimeError",
        "Traceback",
        "File \"",  # cualquier ruta de archivo de un traceback de Python
    ]
    for fragmento in fragmentos_prohibidos:
        assert fragmento not in texto_completo_de_la_respuesta, (
            f"El fragmento sensible {fragmento!r} se filtró en la respuesta al cliente."
        )


def test_ruta_inexistente_devuelve_404_con_el_mismo_contrato_de_error(
    client: TestClient,
) -> None:
    """
    Incluso un 404 de Starlette (ruta que no existe en absoluto, no un
    recurso de negocio) respeta el contrato uniforme de error.
    """
    respuesta = client.get("/esta-ruta-no-existe")

    assert respuesta.status_code == 404
    cuerpo = respuesta.json()
    assert set(cuerpo.keys()) >= {"tipo", "titulo", "estado", "correlation_id"}
