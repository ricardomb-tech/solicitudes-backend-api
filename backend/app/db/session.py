"""
Motor de base de datos y gestión de sesiones (SQLAlchemy síncrono, ver ADR-0007).
"""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    # pool_pre_ping: antes de entregar una conexión del pool, envía un "ping"
    # barato para comprobar que sigue viva. Sin esto, una conexión que el
    # servidor (o un balanceador/proxy intermedio) cerró por inactividad se
    # entrega igualmente y la primera consulta falla. Es especialmente
    # relevante de cara a RDS en AWS, donde hay timeouts de red intermedios.
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    # echo=False: no volcar el SQL crudo al log. El logging estructurado del
    # Bloque 3 registra lo que interesa (endpoint, duración, código); el SQL
    # completo en producción es ruido y puede filtrar datos sensibles.
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
