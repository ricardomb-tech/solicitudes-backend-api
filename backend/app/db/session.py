"""
Motor de base de datos y gestión de sesiones (SQLAlchemy síncrono, ver ADR-0007).
"""
from collections.abc import Iterator

import structlog
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

settings = get_settings()

engine = create_engine(
    settings.database_url,
    # pool_pre_ping: antes de entregar una conexión del pool, envía un "ping"
    # barato para comprobar que sigue viva. Sin esto, una conexión que el
    # servidor (o un balanceador/proxy intermedio) cerró por inactividad se
    # entrega igualmente y la primera consulta falla. Es especialmente
    # relevante de cara a RDS en AWS, donde hay timeouts de red intermedios.
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=10,
    # pool_timeout: sin este valor, una petición que no consigue conexión
    # espera el default de SQLAlchemy (30s) antes de fallar. Con un valor
    # corto, el agotamiento del pool se convierte en un 503 rápido y
    # accionable (ver mapeo en error_handlers.py) en vez de una petición
    # colgada que además retiene el hilo del threadpool de AnyIO.
    pool_timeout=5,
    # pool_recycle: recicla conexiones con más de 30 min, evitando que se
    # acumulen conexiones a punto de ser cerradas por el servidor (o por un
    # proxy intermedio como PgBouncer/RDS Proxy en AWS) sin que el pool lo note.
    pool_recycle=1800,
    connect_args={
        "connect_timeout": 5,
        # statement_timeout: sin tope, una consulta bloqueada (por un lock de
        # otra transacción, un plan degenerado, etc.) retiene su conexión
        # indefinidamente. Con 10 de conexiones en el pool, unas pocas
        # consultas colgadas bastan para inutilizar el servicio completo,
        # incluido /health/ready, que compite por el mismo pool.
        # idle_in_transaction_session_timeout: corta una transacción que
        # quedó abierta sin actividad (p. ej. por un bug que olvida hacer
        # commit/rollback), liberando la conexión y evitando que bloquee al
        # autovacuum de PostgreSQL.
        "options": "-c statement_timeout=5000 -c idle_in_transaction_session_timeout=10000",
    },
    # echo=False: no volcar el SQL crudo al log. El middleware de logging
    # estructurado (app/core/middleware.py) ya registra lo que interesa
    # (endpoint, duración, código); el SQL completo en producción es ruido y
    # puede filtrar datos sensibles.
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    # expire_on_commit=False: tras un commit, SQLAlchemy por defecto marca los
    # objetos como "expirados" y vuelve a consultarlos en el siguiente acceso
    # a cualquier atributo. Como después de crear/actualizar necesitamos
    # serializar el objeto a JSON (lo que accede a todos sus atributos), eso
    # provocaría una consulta extra innecesaria por cada escritura.
    expire_on_commit=False,
)


def get_db() -> Iterator[Session]:
    """
    Dependencia de FastAPI: entrega una sesión por petición y garantiza su
    cierre al terminar, incluso si el handler lanza una excepción.

    Una sesión por petición (y no una sesión global compartida) es lo que
    permite que dos peticiones concurrentes tengan transacciones
    independientes — requisito directo del manejo de concurrencia (ADR-0003).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verificar_conexion(session: Session) -> bool:
    """
    Comprueba que la sesión puede ejecutar una consulta trivial contra
    PostgreSQL. Usada por el endpoint de readiness (`/health/ready`).

    Vive aquí, y no en el router, porque ADR-0001 fija como regla objetiva
    que ningún router importe `sqlalchemy` directamente: el router solo debe
    conocer "¿la base de datos responde sí o no?", nunca `text("SELECT 1")`
    ni el tipo de excepción del motor. (Esta función corrige exactamente una
    violación de esa regla, detectada en una auditoría posterior: el propio
    endpoint de salud era el único punto del proyecto que la incumplía.)

    Se ejecuta `SELECT 1` —la consulta más barata posible que aun así recorre
    el camino completo (pool → red → servidor → respuesta)— y no una consulta
    sobre una tabla del negocio: el chequeo debe verificar conectividad, no
    depender de que exista determinado dato.
    """
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.error("verificacion_conexion_fallida", exc_info=True)
        return False
    return True
