"""
Pruebas de POST /solicitudes: creación válida, rechazo de datos inválidos y
manejo de duplicados (REQ-P-01, REQ-P-02, REQ-P-03).
"""
import uuid

import pytest
from fastapi.testclient import TestClient


def test_crear_solicitud_valida_devuelve_201_con_estado_inicial_recibida(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    respuesta = client.post("/solicitudes", json=solicitud_valida_payload)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()

    # El sistema asigna id y estado; el cliente no los envía ni los controla.
    uuid.UUID(cuerpo["id"])  # no lanza si es un UUID válido
    assert cuerpo["estado"] == "recibida"

    # Los demás campos son eco de lo enviado.
    assert cuerpo["identificador_externo"] == solicitud_valida_payload["identificador_externo"]
    assert cuerpo["tipo"] == solicitud_valida_payload["tipo"]
    assert cuerpo["correo"] == solicitud_valida_payload["correo"]


def test_crear_solicitud_genera_fechas_automaticamente(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    respuesta = client.post("/solicitudes", json=solicitud_valida_payload)
    cuerpo = respuesta.json()

    assert "fecha_creacion" in cuerpo
    assert "fecha_actualizacion" in cuerpo
    # Al crear, ambas fechas son el mismo instante (las genera el mismo
    # `server_default=func.now()` en la misma sentencia INSERT).
    assert cuerpo["fecha_creacion"] == cuerpo["fecha_actualizacion"]


def test_crear_solicitud_devuelve_cabecera_de_correlacion(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    respuesta = client.post("/solicitudes", json=solicitud_valida_payload)

    assert "x-correlation-id" in respuesta.headers


@pytest.mark.parametrize(
    ("campo_a_quitar", "descripcion"),
    [
        ("identificador_externo", "falta identificador_externo"),
        ("tipo", "falta tipo"),
        ("nombre_solicitante", "falta nombre_solicitante"),
        ("correo", "falta correo"),
        ("descripcion", "falta descripcion"),
        ("prioridad", "falta prioridad"),
    ],
)
def test_rechaza_creacion_sin_campo_obligatorio(
    client: TestClient,
    solicitud_valida_payload: dict[str, str],
    campo_a_quitar: str,
    descripcion: str,
) -> None:
    payload = {k: v for k, v in solicitud_valida_payload.items() if k != campo_a_quitar}

    respuesta = client.post("/solicitudes", json=payload)

    assert respuesta.status_code == 422, descripcion
    cuerpo = respuesta.json()
    assert cuerpo["tipo"] == "error_validacion"
    assert any(d["campo"] == campo_a_quitar for d in cuerpo["detalles"])


@pytest.mark.parametrize(
    ("campo", "valor_invalido"),
    [
        ("correo", "esto-no-es-un-correo"),
        ("tipo", "tipo_que_no_existe"),
        ("prioridad", "urgentisima"),
        ("identificador_externo", ""),
        ("nombre_solicitante", ""),
        ("descripcion", ""),
    ],
)
def test_rechaza_creacion_con_valor_invalido(
    client: TestClient,
    solicitud_valida_payload: dict[str, str],
    campo: str,
    valor_invalido: str,
) -> None:
    payload = {**solicitud_valida_payload, campo: valor_invalido}

    respuesta = client.post("/solicitudes", json=payload)

    assert respuesta.status_code == 422
    assert respuesta.json()["tipo"] == "error_validacion"


def test_rechaza_campo_no_declarado_en_el_esquema(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    """
    `extra="forbid"` (ver schemas/solicitud.py): un campo desconocido se
    rechaza en vez de ignorarse en silencio.
    """
    payload = {**solicitud_valida_payload, "campo_que_no_existe": "valor"}

    respuesta = client.post("/solicitudes", json=payload)

    assert respuesta.status_code == 422


def test_no_permite_elegir_el_estado_inicial_al_crear(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    """
    El esquema de creación no incluye "estado" (ver D2.7): intentar enviarlo
    se trata como un campo no declarado y se rechaza, precisamente para que
    nadie pueda crear una solicitud ya "completada".
    """
    payload = {**solicitud_valida_payload, "estado": "completada"}

    respuesta = client.post("/solicitudes", json=payload)

    assert respuesta.status_code == 422


def test_crear_solicitud_con_identificador_duplicado_devuelve_409(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    primera = client.post("/solicitudes", json=solicitud_valida_payload)
    assert primera.status_code == 201

    payload_duplicado = {
        **solicitud_valida_payload,
        # Todo lo demás cambia; solo el identificador externo se repite.
        "nombre_solicitante": "Otra Persona",
        "correo": "otra.persona@institucion.edu.co",
    }
    segunda = client.post("/solicitudes", json=payload_duplicado)

    assert segunda.status_code == 409
    cuerpo = segunda.json()
    assert cuerpo["tipo"] == "solicitud_duplicada"
    assert cuerpo["detalles"][0]["campo"] == "identificador_externo"


def test_duplicado_no_crea_un_segundo_registro_en_la_base_de_datos(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    client.post("/solicitudes", json=solicitud_valida_payload)
    client.post("/solicitudes", json=solicitud_valida_payload)  # se rechaza

    respuesta = client.get(
        "/solicitudes",
        params={"identificador_externo": solicitud_valida_payload["identificador_externo"]},
    )

    assert respuesta.json()["total"] == 1
