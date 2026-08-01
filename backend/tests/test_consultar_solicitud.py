"""
Pruebas de GET /solicitudes y GET /solicitudes/{id}: consulta de registros
existentes e inexistentes, filtros y paginación (REQ-P-04).
"""
import uuid

from fastapi.testclient import TestClient


def test_obtener_solicitud_existente_por_id(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    creada = client.post("/solicitudes", json=solicitud_valida_payload).json()

    respuesta = client.get(f"/solicitudes/{creada['id']}")

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == creada["id"]
    assert respuesta.json()["identificador_externo"] == solicitud_valida_payload["identificador_externo"]


def test_obtener_solicitud_inexistente_devuelve_404(client: TestClient) -> None:
    id_inexistente = uuid.uuid4()

    respuesta = client.get(f"/solicitudes/{id_inexistente}")

    assert respuesta.status_code == 404
    assert respuesta.json()["tipo"] == "solicitud_no_encontrada"


def test_obtener_con_id_mal_formado_devuelve_422_sin_tocar_la_base_de_datos(
    client: TestClient,
) -> None:
    respuesta = client.get("/solicitudes/esto-no-es-un-uuid")

    assert respuesta.status_code == 422


def test_listar_sin_filtro_devuelve_todas_las_solicitudes_paginadas(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    for i in range(3):
        payload = {
            **solicitud_valida_payload,
            "identificador_externo": f"{solicitud_valida_payload['identificador_externo']}-{i}",
        }
        client.post("/solicitudes", json=payload)

    respuesta = client.get("/solicitudes")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 3
    assert len(cuerpo["items"]) == 3


def test_listar_filtra_por_estado(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    creada = client.post("/solicitudes", json=solicitud_valida_payload).json()
    client.patch(f"/solicitudes/{creada['id']}/estado", json={"estado": "en_proceso"})

    otra_payload = {**solicitud_valida_payload, "identificador_externo": "SOL-OTRA-001"}
    client.post("/solicitudes", json=otra_payload)  # se queda en "recibida"

    respuesta = client.get("/solicitudes", params={"estado": "en_proceso"})

    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["id"] == creada["id"]


def test_listar_filtra_por_tipo_y_prioridad_combinados(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    coincide = {
        **solicitud_valida_payload,
        "identificador_externo": "SOL-COMBINADO-001",
        "tipo": "academica",
        "prioridad": "baja",
    }
    no_coincide_tipo = {
        **solicitud_valida_payload,
        "identificador_externo": "SOL-COMBINADO-002",
        "tipo": "administrativa",
        "prioridad": "baja",
    }
    no_coincide_prioridad = {
        **solicitud_valida_payload,
        "identificador_externo": "SOL-COMBINADO-003",
        "tipo": "academica",
        "prioridad": "alta",
    }
    for payload in (coincide, no_coincide_tipo, no_coincide_prioridad):
        client.post("/solicitudes", json=payload)

    respuesta = client.get(
        "/solicitudes", params={"tipo": "academica", "prioridad": "baja"}
    )

    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["identificador_externo"] == "SOL-COMBINADO-001"


def test_listar_respeta_limit_y_offset(
    client: TestClient, solicitud_valida_payload: dict[str, str]
) -> None:
    for i in range(5):
        payload = {
            **solicitud_valida_payload,
            "identificador_externo": f"SOL-PAGINA-{i}",
        }
        client.post("/solicitudes", json=payload)

    pagina_1 = client.get("/solicitudes", params={"limit": 2, "offset": 0}).json()
    pagina_2 = client.get("/solicitudes", params={"limit": 2, "offset": 2}).json()

    assert pagina_1["total"] == 5
    assert len(pagina_1["items"]) == 2
    assert len(pagina_2["items"]) == 2
    # Las dos páginas no deben repetir elementos.
    ids_pagina_1 = {item["id"] for item in pagina_1["items"]}
    ids_pagina_2 = {item["id"] for item in pagina_2["items"]}
    assert ids_pagina_1.isdisjoint(ids_pagina_2)


def test_listar_rechaza_limit_mayor_al_maximo_permitido(client: TestClient) -> None:
    """
    El tope de página lo impone el servidor (settings.max_page_size), no la
    confianza en el cliente — evita que `?limit=1000000` agote memoria.
    """
    respuesta = client.get("/solicitudes", params={"limit": 99999})

    assert respuesta.status_code == 422
