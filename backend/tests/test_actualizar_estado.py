"""
Pruebas de PATCH /solicitudes/{id}/estado: máquina de estados, idempotencia y
actualización de fecha_actualizacion (REQ-P-05).
"""
import time
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("estado_origen", "estado_destino"),
    [
        ("recibida", "en_proceso"),
        ("recibida", "rechazada"),
        ("en_proceso", "completada"),
        ("en_proceso", "rechazada"),
    ],
)
def test_transiciones_permitidas_devuelven_200(
    client: TestClient,
    solicitud_valida_payload: dict[str, str],
    estado_origen: str,
    estado_destino: str,
) -> None:
    creada = client.post("/solicitudes", json=solicitud_valida_payload).json()

    if estado_origen != "recibida":
        client.patch(f"/solicitudes/{creada['id']}/estado", json={"estado": estado_origen})

    respuesta = client.patch(
        f"/solicitudes/{creada['id']}/estado", json={"estado": estado_destino}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == estado_destino


@pytest.mark.parametrize(
    ("estado_origen", "estado_destino"),
    [
        ("recibida", "completada"),  # salta "en_proceso"
        ("completada", "recibida"),  # retrocede desde un estado terminal
        ("completada", "en_proceso"),
        ("rechazada", "recibida"),
        ("rechazada", "en_proceso"),
    ],
)
def test_transiciones_no_permitidas_devuelven_409(
    client: TestClient,
    solicitud_valida_payload: dict[str, str],
    estado_origen: str,
    estado_destino: str,
) -> None:
    creada = client.post("/solicitudes", json=solicitud_valida_payload).json()

    # Lleva la solicitud hasta estado_origen a través de transiciones válidas.
    camino = {
        "recibida": [],
        "en_proceso": ["en_proceso"],
        "completada": ["en_proceso", "completada"],
        "rechazada": ["rechazada"],
    }[estado_origen]
    for paso in camino:
        client.patch(f"/solicitudes/{creada['id']}/estado", json={"estado": paso})

    respuesta = client.patch(
        f"/solicitudes/{creada['id']}/estado", json={"estado": estado_destino}
    )

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "transicion_estado_invalida"
    assert cuerpo["detalles"][0]["estado_actual"] == estado_origen
    assert cuerpo["detalles"][0]["estado_solicitado"] == estado_destino


def test_reenviar_el_mismo_estado_es_idempotente_y_no_falla(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    creada = client.post("/solicitudes", json=solicitud_valida_payload).json()
    client.patch(f"/solicitudes/{creada['id']}/estado", json={"estado": "en_proceso"})

    respuesta = client.patch(
        f"/solicitudes/{creada['id']}/estado", json={"estado": "en_proceso"}
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "en_proceso"


def test_reenviar_el_mismo_estado_no_modifica_fecha_actualizacion(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    creada = client.post("/solicitudes", json=solicitud_valida_payload).json()
    primer_cambio = client.patch(
        f"/solicitudes/{creada['id']}/estado", json={"estado": "en_proceso"}
    ).json()

    time.sleep(0.05)
    segundo_intento = client.patch(
        f"/solicitudes/{creada['id']}/estado", json={"estado": "en_proceso"}
    ).json()

    # No hubo escritura real la segunda vez: la fecha no cambia.
    assert segundo_intento["fecha_actualizacion"] == primer_cambio["fecha_actualizacion"]


def test_transicion_valida_actualiza_fecha_actualizacion(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    creada = client.post("/solicitudes", json=solicitud_valida_payload).json()

    time.sleep(0.05)
    actualizada = client.patch(
        f"/solicitudes/{creada['id']}/estado", json={"estado": "en_proceso"}
    ).json()

    assert actualizada["fecha_actualizacion"] > creada["fecha_actualizacion"]
    # La fecha de creación nunca cambia.
    assert actualizada["fecha_creacion"] == creada["fecha_creacion"]


def test_actualizar_estado_de_solicitud_inexistente_devuelve_404(
    client: TestClient,
) -> None:
    respuesta = client.patch(
        f"/solicitudes/{uuid.uuid4()}/estado", json={"estado": "en_proceso"}
    )

    assert respuesta.status_code == 404
    assert respuesta.json()["tipo"] == "solicitud_no_encontrada"


def test_actualizar_estado_con_valor_de_catalogo_invalido_devuelve_422(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    creada = client.post("/solicitudes", json=solicitud_valida_payload).json()

    respuesta = client.patch(
        f"/solicitudes/{creada['id']}/estado", json={"estado": "estado_inventado"}
    )

    assert respuesta.status_code == 422
