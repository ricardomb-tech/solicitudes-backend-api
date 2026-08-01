"""Modelo ORM de la entidad Solicitud."""
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import ESTADO_INICIAL, EstadoSolicitud, Prioridad, TipoSolicitud


def _check_en_catalogo(columna: str, enum_cls: type) -> str:
    """
    Construye la expresión SQL de un CHECK a partir del Enum de dominio.

    Se genera desde el Enum en lugar de escribir la lista de valores a mano
    para que exista una sola fuente de verdad (app/domain/enums.py) en el
    CÓDIGO: si se agrega un valor al catálogo, esta función ya produce la
    expresión SQL correcta la próxima vez que se ejecute.

    ADVERTENCIA REAL, encontrada en auditoría — leer antes de agregar un
    valor de catálogo en vivo (p. ej. durante la sustentación):
    `alembic revision --autogenerate` NO detecta cambios en restricciones
    `CHECK` (solo compara tablas, columnas e índices). Agregar un miembro al
    Enum y correr `--autogenerate` genera una migración VACÍA — sin avisar de
    que no vio el cambio. El paso manual obligatorio es escribir la migración
    a mano con:

        op.drop_constraint("ck_solicitudes_tipo", "solicitudes")
        op.create_check_constraint(
            "ck_solicitudes_tipo", "solicitudes", _check_en_catalogo("tipo", TipoSolicitud)
        )

    Como red de seguridad adicional (no como sustituto de lo anterior): si
    este paso se olvida, `app/core/error_handlers.py::manejar_error_integridad`
    intercepta el `IntegrityError` resultante y responde `422` en vez de un
    `500` opaco — pero el arreglo correcto sigue siendo escribir la migración.
    """
    valores = ", ".join(f"'{miembro.value}'" for miembro in enum_cls)
    return f"{columna} IN ({valores})"


class Solicitud(Base):
    __tablename__ = "solicitudes"

    # --- Identidad -----------------------------------------------------------
    # UUID como clave primaria (ver ADR-0002): evita enumeración secuencial de
    # recursos y desacopla la identidad interna del identificador del sistema
    # de origen. `gen_random_uuid()` es nativo en PostgreSQL 13+ (no requiere
    # la extensión pgcrypto), y generarlo en la base de datos mantiene el
    # criterio de que la identidad la asigna el sistema, no el cliente.
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Identificador asignado por el sistema de origen. `unique=True` genera la
    # restricción UNIQUE en la base de datos, que es el mecanismo que garantiza
    # la ausencia de duplicados incluso bajo peticiones concurrentes: es el
    # motor quien serializa las escrituras (ver ADR-0003).
    identificador_externo: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )

    # --- Datos de negocio ----------------------------------------------------
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre_solicitante: Mapped[str] = mapped_column(String(150), nullable=False)
    # 254 = longitud máxima de una dirección de correo según RFC 5321.
    correo: Mapped[str] = mapped_column(String(254), nullable=False)
    # String(4000), no Text: el esquema Pydantic ya limita a 4000 caracteres
    # (ver schemas/solicitud.py); la columna refleja el mismo límite como red
    # de seguridad en la base de datos, coherente con el resto de campos de
    # texto del modelo (todos con longitud acotada, ninguno sin límite).
    descripcion: Mapped[str] = mapped_column(String(4000), nullable=False)
    prioridad: Mapped[str] = mapped_column(String(10), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(15), nullable=False, server_default=text(f"'{ESTADO_INICIAL.value}'")
    )

    # --- Fechas administradas por el sistema ---------------------------------
    # TIMESTAMPTZ (timezone=True), no TIMESTAMP: un instante sin zona horaria
    # es ambiguo en cuanto la aplicación corre en más de una región o el
    # servidor cambia de huso. PostgreSQL almacena TIMESTAMPTZ normalizado en
    # UTC.
    #
    # server_default=func.now(): la fecha la genera el MOTOR, no Python. El
    # enunciado pide que las fechas las administre el sistema; si cada réplica
    # de la aplicación pusiera su propio reloj, un desfase entre instancias
    # produciría un ordenamiento temporal inconsistente. El reloj de la base de
    # datos es la única fuente de verdad compartida.
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # onupdate=func.now(): SQLAlchemy incluye `now()` en la sentencia UPDATE,
    # de modo que la evaluación también ocurre en el servidor.
    #
    # Limitación conocida y asumida: `onupdate` solo aplica a los UPDATE que
    # pasan por SQLAlchemy. Una actualización hecha con SQL manual directo
    # sobre la tabla no refrescaría esta columna. Cubrirlo por completo exigiría
    # un trigger `BEFORE UPDATE` en la base de datos; se descarta por ahora
    # porque toda escritura del sistema pasa por la aplicación, y se documenta
    # aquí para que sea una decisión consciente y no un descuido.
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # --- Integridad de catálogos ----------------------------------------
        # Los valores permitidos se validan en dos capas, deliberadamente:
        #   1. Pydantic, en el borde HTTP: rechaza la petición con 422 y un
        #      mensaje útil antes de tocar la base de datos.
        #   2. CHECK en la base de datos: red de seguridad ante cualquier
        #      escritura que no pase por la capa de esquemas (una migración
        #      mal hecha, un script de carga, SQL manual).
        # Duplicar la regla no es redundancia inútil: cada capa protege contra
        # un modo de fallo distinto.
        CheckConstraint(
            _check_en_catalogo("tipo", TipoSolicitud), name="ck_solicitudes_tipo"
        ),
        CheckConstraint(
            _check_en_catalogo("prioridad", Prioridad),
            name="ck_solicitudes_prioridad",
        ),
        CheckConstraint(
            _check_en_catalogo("estado", EstadoSolicitud), name="ck_solicitudes_estado"
        ),
        # --- Índices de consulta --------------------------------------------
        # Índice COMPUESTO, no tres índices sueltos: el caso de uso declarado
        # en el enunciado filtra por estado, tipo y prioridad de forma
        # combinada. Un índice compuesto sirve además a los prefijos
        # (estado) y (estado, tipo) por la propiedad "leftmost prefix" del
        # árbol B, cubriendo los filtros parciales más frecuentes con una sola
        # estructura. Tres índices independientes obligarían al planificador a
        # combinarlos (bitmap AND) y encarecerían cada escritura por triplicado.
        Index(
            "ix_solicitudes_estado_tipo_prioridad",
            "estado",
            "tipo",
            "prioridad",
        ),
        # Orden por defecto del listado (más recientes primero): un índice
        # descendente evita un ordenamiento en memoria sobre el resultado.
        Index(
            "ix_solicitudes_fecha_creacion_desc",
            text("fecha_creacion DESC"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Solicitud id={self.id} "
            f"identificador_externo={self.identificador_externo!r} "
            f"estado={self.estado!r}>"
        )
