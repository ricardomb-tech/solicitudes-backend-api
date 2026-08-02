"""
Modelo ORM de la entidad Solicitud — la única capa que habla SQLAlchemy.

En la arquitectura de cuatro capas (ADR-0001), este módulo es la capa más
interna: define la correspondencia entre el objeto Python y la tabla de la
base de datos. La regla mecánica que verifica que la separación es real y no
solo decorativa: ningún archivo fuera de `models/` y `repositories/` importa
`sqlalchemy`; el service y el router no saben que existe.

La fuente de verdad de los valores de negocio (tipos, prioridades, estados,
máquina de transiciones) no está aquí: está en `app/domain/enums.py`. Este
módulo la consume para construir las restricciones `CHECK` de la base de datos,
pero no la duplica. Si se cometiera el error de escribir los valores dos veces
—una en el Enum y otra aquí como literales de texto— cualquier cambio de
catálogo exigiría actualizar dos sitios, y el primero que se olvide produce una
inconsistencia silenciosa entre la validación de la aplicación y la de la BD.

Relación con Alembic (ADR-0004): este archivo dirige la generación automática
de migraciones. `alembic revision --autogenerate` compara el estado de los
modelos declarados aquí contra el esquema real de la base de datos y produce
el SQL de diferencia. El proceso tiene una limitación importante que se documenta
en `_check_en_catalogo()` y debe leerse antes de agregar cualquier valor a un
catálogo.
"""
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

    Por qué `String` + `CHECK` y no un tipo `ENUM` nativo de PostgreSQL:
    los ENUM nativos son difíciles de alterar en producción —agregar o eliminar
    un valor requiere una operación DDL que no es transaccional en todas las
    versiones de PostgreSQL y no puede revertirse con `alembic downgrade`. Con
    `String` + `CHECK`, cambiar un catálogo es: editar el Enum en Python y
    escribir una migración que suelte y vuelva a crear la restricción. Más
    verboso, pero más seguro y reversible.

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
    """
    Representación ORM de una solicitud institucional.

    Encarna dos identidades distintas para la misma entidad (ADR-0002):
    - `id`: clave primaria técnica (UUID generado por el sistema). Es el
      identificador que aparece en las rutas REST (`/solicitudes/{id}`) y en
      los logs de correlación. El cliente nunca lo elige.
    - `identificador_externo`: clave de negocio asignada por el sistema de
      origen. Es el identificador que el consumidor envía y que debe ser único
      en toda la tabla.

    Separarlos no es burocracia: si `identificador_externo` fuera la PK, el
    modelo de datos interno quedaría acoplado a un código cuyo formato y
    unicidad dependen de un sistema que no controlamos. Si ese sistema cambiara
    su esquema de numeración, habría que migrar la clave primaria de la tabla
    —operación costosa y riesgosa en producción.

    Nota sobre SQLAlchemy síncrono (ADR-0007): el modelo declara columnas con
    la API `Mapped` / `mapped_column` de SQLAlchemy 2.0, que funciona igual
    en el modo síncrono y asíncrono. La elección de usar `Session` síncrona
    (y endpoints FastAPI como `def`, no `async def`) se documenta en ADR-0007;
    no afecta ninguna línea de este archivo, pero sí el `db/session.py` que
    provee las sesiones y los routers que los consumen.
    """

    __tablename__ = "solicitudes"

    # --- Identidad -----------------------------------------------------------

    # UUID como clave primaria (ADR-0002): evita la enumeración secuencial de
    # recursos que permitiría un `SERIAL`. Con un entero autoincremental, un
    # cliente curioso puede hacer GET /solicitudes/1, /2, /3 y estimar el
    # volumen de negocio o iterar sobre todos los registros sin ningún permiso
    # (IDOR por enumeración — un antipatrón de seguridad conocido).
    #
    # `gen_random_uuid()` nativo de PostgreSQL 13+ (no requiere la extensión
    # pgcrypto). Generarlo en la base de datos en lugar de en Python garantiza
    # que todas las réplicas de la aplicación usen el mismo reloj y el mismo
    # generador, sin riesgo de colisión por estados de proceso distintos.
    #
    # Costo asumido: 16 bytes por fila en lugar de 4-8 de un entero, y peor
    # localidad de escritura en el índice B-tree (los inserts no son "al final"
    # del árbol como sí lo son con un autoincremental). A la escala de un
    # sistema de gestión de solicitudes institucionales, ese costo es
    # irrelevante frente al beneficio de seguridad y desacoplamiento.
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    # Identificador asignado por el sistema de origen — es la clave de negocio,
    # no la clave técnica. `unique=True` genera la restricción `UNIQUE` real en
    # la base de datos: es el único mecanismo verdaderamente atómico para
    # garantizar ausencia de duplicados bajo peticiones concurrentes (ADR-0003).
    #
    # La alternativa ingenua —consultar si existe con SELECT y luego insertar si
    # no— tiene una ventana TOCTOU (time-of-check to time-of-use): entre el
    # SELECT y el INSERT, otra petición concurrente puede haber insertado el
    # mismo valor. El resultado es o bien un `IntegrityError` no manejado (500)
    # o, peor, un duplicado real si no hay restricción a nivel de base de datos.
    # La restricción UNIQUE en el motor es lo que cierra esa ventana sin
    # necesidad de locks manuales.
    identificador_externo: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )

    # --- Datos de negocio ----------------------------------------------------

    # Los tres catálogos (tipo, prioridad, estado) se almacenan como `String`
    # en lugar de usar el tipo `ENUM` nativo de PostgreSQL: ver la justificación
    # en `_check_en_catalogo()`. Los `CHECK` de `__table_args__` son la segunda
    # capa de defensa; `app/domain/enums.py` es la fuente de verdad de los
    # valores permitidos.
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre_solicitante: Mapped[str] = mapped_column(String(150), nullable=False)
    # 254 = longitud máxima de una dirección de correo según RFC 5321.
    correo: Mapped[str] = mapped_column(String(254), nullable=False)
    # String(4000), no Text: el esquema Pydantic limita la descripción a 4 000
    # caracteres (ver `schemas/solicitud.py`). La columna refleja el mismo límite
    # como red de seguridad en la base de datos: si en algún momento una
    # escritura evitara la capa Pydantic (script de carga, migración de datos),
    # la base de datos rechaza de igual modo cualquier valor fuera de rango.
    descripcion: Mapped[str] = mapped_column(String(4000), nullable=False)
    prioridad: Mapped[str] = mapped_column(String(10), nullable=False)

    # El estado inicial lo impone el sistema, no el cliente. Si el cliente
    # pudiera elegirlo, podría crear una solicitud ya marcada como "completada",
    # saltándose todo el flujo de atención. `server_default` toma el valor de
    # `ESTADO_INICIAL` (definido en `domain/enums.py`) en lugar de hardcodear
    # la cadena "recibida": si el estado inicial cambiara, el cambio ocurre en
    # un solo lugar y tanto la validación de la aplicación como el default de la
    # base de datos se actualizan juntos.
    estado: Mapped[str] = mapped_column(
        String(15), nullable=False, server_default=text(f"'{ESTADO_INICIAL.value}'")
    )

    # --- Fechas administradas por el sistema ---------------------------------

    # `DateTime(timezone=True)` → columna `TIMESTAMPTZ` en PostgreSQL, no
    # `TIMESTAMP` sin zona. Un instante sin zona horaria es ambiguo en cuanto
    # la aplicación corre en más de una región o el servidor cambia de huso
    # horario. PostgreSQL almacena `TIMESTAMPTZ` normalizado en UTC y convierte
    # al presentar, garantizando que dos registros creados con cinco segundos de
    # diferencia siempre se ordenen correctamente, sin importar en qué zona
    # corra cada réplica.
    #
    # `server_default=func.now()` → la fecha la genera el MOTOR, no Python. Si
    # cada réplica de la aplicación pusiera su propio reloj (`datetime.utcnow()`
    # en Python), un desfase de milisegundos entre instancias produciría un
    # ordenamiento temporal inconsistente. El reloj de la base de datos es la
    # única fuente de tiempo compartida entre todos los procesos.
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # `onupdate=func.now()` → SQLAlchemy inyecta `now()` en la sentencia UPDATE,
    # de modo que la evaluación también ocurre en el servidor (no en Python).
    #
    # Limitación conocida y asumida: `onupdate` solo aplica a los UPDATE que
    # pasan por SQLAlchemy. Una actualización hecha con SQL directo sobre la
    # tabla no refrescaría esta columna. Cubrirlo por completo exigiría un
    # trigger `BEFORE UPDATE` en la base de datos. Se descarta por ahora porque
    # toda escritura del sistema pasa por la aplicación; se documenta aquí para
    # que sea una decisión consciente y no un descuido.
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # --- Integridad de catálogos -----------------------------------------
        # Los valores permitidos se validan en dos capas, deliberadamente:
        #   1. Pydantic, en el borde HTTP: rechaza la petición con 422 y un
        #      mensaje útil ANTES de tocar la base de datos.
        #   2. CHECK en la base de datos: red de seguridad ante cualquier
        #      escritura que no pase por la capa de esquemas (una migración de
        #      datos, un script de carga, SQL manual de administración).
        #
        # Duplicar la regla no es redundancia inútil: cada capa protege contra
        # un modo de fallo distinto. Pydantic atrapa el error antes de que
        # consuma una conexión de base de datos; el CHECK garantiza el invariante
        # incluso si alguien escribe directamente en la tabla.
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
        # --- Índices de consulta ---------------------------------------------
        # Índice COMPUESTO, no tres índices separados: el caso de uso declarado
        # en el enunciado filtra por estado, tipo y prioridad de forma combinada.
        # Un índice compuesto sobre (estado, tipo, prioridad) cubre además los
        # prefijos (estado) y (estado, tipo) por la propiedad "leftmost prefix"
        # del árbol B, sirviendo los filtros parciales más frecuentes con una
        # sola estructura. Si se crearan tres índices independientes, el
        # planificador tendría que combinarlos mediante bitmap AND para consultas
        # combinadas, y cada escritura incurriría en el costo de mantener tres
        # índices por separado.
        Index(
            "ix_solicitudes_estado_tipo_prioridad",
            "estado",
            "tipo",
            "prioridad",
        ),
        # Orden por defecto del listado (más recientes primero): el índice
        # descendente permite que PostgreSQL entregue las filas ya ordenadas,
        # evitando el paso de ordenación en memoria sobre el resultado completo
        # cuando el cliente no aplica filtros adicionales.
        Index(
            "ix_solicitudes_fecha_creacion_desc",
            text("fecha_creacion DESC"),
        ),
    )

    def __repr__(self) -> str:
        """Representación mínima para logs y depuración: id, clave externa y estado."""
        return (
            f"<Solicitud id={self.id} "
            f"identificador_externo={self.identificador_externo!r} "
            f"estado={self.estado!r}>"
        )
