"""
Prueba de concurrencia real sobre `identificador_externo` (ADR-0003).

--- Por qué esta prueba corre contra la capa de SERVICIOS con hilos y
    conexiones independientes, y no a través de TestClient ---

La garantía de atomicidad la da PostgreSQL (la restricción UNIQUE y
`ON CONFLICT`), no el transporte HTTP. Usar hilos con sesiones/conexiones de
base de datos independientes reproduce fielmente el escenario real: dos
procesos de la aplicación (por ejemplo, dos réplicas en Kubernetes/ECS)
compitiendo por el mismo identificador externo.

Se descartó enviar los hilos a través de `TestClient`: Starlette ejecuta el
cliente de pruebas sobre un único *event loop* corrido en un hilo de fondo
(un "portal"), lo que introduce riesgo de que las peticiones queden
serializadas en la práctica sin que eso sea evidente ni controlable desde el
test — produciendo una prueba "verde" que en realidad no ejerció una
condición de carrera real. Ejercer la carrera directamente sobre la capa de
servicios, con hilos de Python reales y una sesión de SQLAlchemy por hilo, es
la forma correcta y determinista de probar una garantía que pertenece a la
base de datos, no a HTTP.

Esta prueba formaliza como test automatizado la verificación manual descrita
en ADR-0003 (20 hilos, 1 creación, 19 conflictos, 0 excepciones).
"""
import threading
import uuid

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import SolicitudDuplicada
from app.repositories.solicitud import SolicitudRepository
from app.schemas.solicitud import SolicitudCrear
from app.services.solicitud import SolicitudService

N_HILOS = 20


def test_veinte_hilos_simultaneos_mismo_identificador_solo_una_creacion(
    test_engine: Engine, solicitud_valida_payload: dict[str, str]
) -> None:
    identificador_externo = f"SOL-CONCURRENCIA-{uuid.uuid4().hex[:8]}"
    fabrica_sesiones = sessionmaker(bind=test_engine)

    barrera = threading.Barrier(N_HILOS)
    resultados: list[str] = []
    errores: list[str] = []
    lock = threading.Lock()

    def intentar_crear(indice: int) -> None:
        datos = SolicitudCrear(
            **{
                **solicitud_valida_payload,
                "identificador_externo": identificador_externo,
                "correo": f"usuario{indice}@institucion.edu.co",
            }
        )
        sesion = fabrica_sesiones()
        try:
            # Todos los hilos esperan aquí y arrancan a la vez: maximiza el
            # solape real entre las transacciones.
            barrera.wait()
            servicio = SolicitudService(SolicitudRepository(sesion), sesion)
            servicio.crear(datos)
            with lock:
                resultados.append("CREADA")
        except SolicitudDuplicada:
            with lock:
                resultados.append("CONFLICTO")
        except Exception as exc:  # noqa: BLE001 - se reporta cualquier fallo inesperado
            with lock:
                errores.append(f"{type(exc).__name__}: {exc}")
        finally:
            sesion.close()

    hilos = [threading.Thread(target=intentar_crear, args=(i,)) for i in range(N_HILOS)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert errores == [], f"Hubo excepciones no controladas: {errores}"
    assert resultados.count("CREADA") == 1, (
        f"Se esperaba exactamente 1 creación, hubo {resultados.count('CREADA')}"
    )
    assert resultados.count("CONFLICTO") == N_HILOS - 1

    # Verificación final directamente en la base de datos: no debe haber
    # quedado ningún duplicado real, más allá de lo que reportó cada hilo.
    with test_engine.connect() as conexion:
        from sqlalchemy import text

        total_en_bd = conexion.execute(
            text(
                "SELECT COUNT(*) FROM solicitudes WHERE identificador_externo = :ident"
            ),
            {"ident": identificador_externo},
        ).scalar_one()
    assert total_en_bd == 1
