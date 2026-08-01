"""
Configuración compartida de las pruebas (ver ADR-0011).

Resumen del enfoque:

1. Las pruebas corren contra PostgreSQL REAL, en una base de datos separada
   (`solicitudes_test`) dentro del mismo servidor que usa la aplicación — no
   contra SQLite ni contra sesiones simuladas. La razón está en ADR-0011: el
   comportamiento que más interesa verificar (restricciones UNIQUE, CHECK,
   resolución de conflictos con ON CONFLICT) depende del motor real.

2. El esquema de la base de datos de pruebas se crea ejecutando el MISMO
   Alembic que se usaría en producción (`alembic upgrade head`), no
   `Base.metadata.create_all()`. Así una migración con un error real se
   detecta en las pruebas, no solo al desplegar.

3. Cada prueba recibe la tabla vacía: un fixture automático la trunca al
   finalizar. Esto evita que el orden de ejecución de las pruebas afecte sus
   resultados (una prueba de "listar" no debe ver datos de otra prueba).

4. La aplicación FastAPI se construye una sola vez por sesión de pruebas y se
   le sustituye la dependencia `get_db` para que use la base de datos de
   pruebas en lugar de la de desarrollo — sin tocar una sola línea de
   `app/`. Esto es exactamente el propósito de que `deps.py` centralice la
   inyección de dependencias (ver comentario en ese archivo).
"""
import os
import subprocess
import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import get_db
from app.main import crear_app

settings = get_settings()

_URL_BASE = make_url(settings.database_url)
_NOMBRE_BD_PRUEBA = "solicitudes_test"
# IMPORTANTE: NO usar str(url) aquí. Desde SQLAlchemy 1.4, str(URL) enmascara
# la contraseña por defecto (para evitar filtrarla accidentalmente en logs),
# devolviendo literalmente "postgresql+psycopg://usuario:***@host/bd". Con eso
# Alembic intentaría autenticarse con la contraseña literal "***" y fallaría
# con "password authentication failed" — un error que además parece (y no es)
# un problema de credenciales reales. render_as_string(hide_password=False)
# es la forma explícita de pedir la contraseña real.
DATABASE_URL_PRUEBA = _URL_BASE.set(database=_NOMBRE_BD_PRUEBA).render_as_string(
    hide_password=False
)


def _crear_base_de_datos_de_prueba_si_no_existe() -> None:
    """
    Se conecta a la base de datos administrativa `postgres` (no se puede crear
    una base de datos estando conectado a ella misma) y crea
    `solicitudes_test` si aún no existe.

    `isolation_level="AUTOCOMMIT"`: PostgreSQL no permite ejecutar
    `CREATE DATABASE` dentro de un bloque de transacción.
    """
    url_admin = _URL_BASE.set(database="postgres")
    engine_admin = create_engine(url_admin, isolation_level="AUTOCOMMIT")
    try:
        with engine_admin.connect() as conexion:
            existe = conexion.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :nombre"),
                {"nombre": _NOMBRE_BD_PRUEBA},
            ).scalar_one_or_none()
            if existe is None:
                # No se puede parametrizar el nombre de una base de datos en
                # DDL; el valor es una constante fija de este archivo, no una
                # entrada externa, por lo que no hay riesgo de inyección SQL.
                conexion.execute(text(f'CREATE DATABASE "{_NOMBRE_BD_PRUEBA}"'))
    finally:
        engine_admin.dispose()


def _aplicar_migraciones_en_bd_de_prueba() -> None:
    """
    Ejecuta `alembic upgrade head` como subproceso, con `DATABASE_URL`
    sobrescrita SOLO para ese proceso hijo (mediante una copia del entorno),
    de modo que la configuración cacheada de la aplicación
    (`get_settings()`, decorada con `lru_cache`) no se ve afectada.
    """
    entorno = {**os.environ, "DATABASE_URL": DATABASE_URL_PRUEBA}
    resultado = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd="/app",
        env=entorno,
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        raise RuntimeError(
            "No se pudieron aplicar las migraciones en la base de datos de "
            f"pruebas.\nstdout:\n{resultado.stdout}\nstderr:\n{resultado.stderr}"
        )


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    """Engine de SQLAlchemy apuntando a `solicitudes_test`, una vez migrada."""
    _crear_base_de_datos_de_prueba_si_no_existe()
    _aplicar_migraciones_en_bd_de_prueba()

    engine = create_engine(DATABASE_URL_PRUEBA, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def _fabrica_sesiones_prueba(test_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session")
def _override_bd_normal(_fabrica_sesiones_prueba: sessionmaker[Session]):
    """
    La sustitución "feliz" de `get_db`: entrega una sesión real contra
    `solicitudes_test`. Se guarda en un fixture propio (en vez de definirla
    inline) para poder restaurarla explícitamente después de que un test
    individual la reemplace temporalmente por una versión que simula un fallo
    (ver test_health.py y test_errores.py).
    """

    def _override() -> Iterator[Session]:
        sesion = _fabrica_sesiones_prueba()
        try:
            yield sesion
        finally:
            sesion.close()

    return _override


@pytest.fixture(scope="session")
def app_instance(_override_bd_normal) -> FastAPI:
    """Una única instancia de la aplicación para toda la sesión de pruebas."""
    aplicacion = crear_app()
    aplicacion.dependency_overrides[get_db] = _override_bd_normal
    return aplicacion


@pytest.fixture
def client(app_instance: FastAPI, _override_bd_normal) -> Iterator[TestClient]:
    """
    Cliente HTTP de pruebas.

    Restaura el override "normal" de `get_db` antes Y después de cada test:
    algunos tests (readiness caída, error 500 simulado) reemplazan la
    dependencia temporalmente para forzar un fallo, y este fixture garantiza
    que ningún test deja ese reemplazo activo para el siguiente.

    `raise_server_exceptions=False`: por defecto, TestClient RE-LANZA en el
    proceso de pruebas cualquier excepción no controlada por la aplicación,
    en vez de devolver la respuesta 500 real — es una ayuda pensada para que
    un desarrollador vea el traceback completo mientras escribe tests del
    camino feliz. Aquí se desactiva a propósito: varios tests (test_errores.py)
    verifican exactamente el comportamiento del manejador de errores ante una
    excepción no controlada, y para eso necesitan la respuesta HTTP real que
    el cliente final recibiría, no la excepción re-lanzada en Python.
    """
    app_instance.dependency_overrides[get_db] = _override_bd_normal
    with TestClient(app_instance, raise_server_exceptions=False) as cliente:
        yield cliente
    app_instance.dependency_overrides[get_db] = _override_bd_normal


@pytest.fixture(autouse=True)
def _tabla_limpia(test_engine: Engine) -> Iterator[None]:
    """
    Garantiza que cada prueba empiece con la tabla `solicitudes` vacía.

    Se trunca DESPUÉS de cada test (no antes): así, si una prueba falla, sus
    datos quedan disponibles para inspección manual con `psql` hasta que
    corra la siguiente prueba.
    """
    yield
    with test_engine.begin() as conexion:
        conexion.execute(text("TRUNCATE TABLE solicitudes RESTART IDENTITY CASCADE"))


@pytest.fixture
def solicitud_valida_payload() -> dict[str, str]:
    """
    Cuerpo válido para POST /solicitudes.

    El identificador externo incluye un sufijo aleatorio para que las pruebas
    que no dependen explícitamente de un valor fijo nunca choquen entre sí por
    casualidad, incluso si el truncado de tabla fallara por algún motivo.
    """
    return {
        "identificador_externo": f"SOL-TEST-{uuid.uuid4().hex[:10]}",
        "tipo": "soporte_tecnico",
        "nombre_solicitante": "Ana María Restrepo",
        "correo": "ana.restrepo@institucion.edu.co",
        "descripcion": "No puedo acceder al portal académico desde el lunes.",
        "prioridad": "alta",
    }
