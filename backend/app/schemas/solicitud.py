"""
Esquemas Pydantic: el contrato público de la API.

Se mantienen SEPARADOS del modelo SQLAlchemy a propósito. Son dos cosas
distintas que evolucionan por razones distintas:

- El modelo ORM describe cómo se ALMACENA la entidad (columnas, índices,
  restricciones).
- El esquema describe qué se ACEPTA y qué se DEVUELVE por HTTP.

Exponer el modelo ORM directamente en la API acopla el contrato público al
esquema de la base de datos: cualquier columna interna que se agregue mañana
(auditoría, banderas técnicas, campos de migración) quedaría publicada sin
querer. Con esquemas explícitos, lo que se expone es una decisión, no un
efecto secundario.

Se definen esquemas distintos para entrada y salida por la misma razón: los
campos que el cliente PUEDE enviar no son los mismos que el servidor devuelve.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domain.enums import EstadoSolicitud, Prioridad, TipoSolicitud


class SolicitudCrear(BaseModel):
    """
    Cuerpo aceptado en POST /solicitudes.

    Nótese qué NO está aquí:
    - `id`, `fecha_creacion`, `fecha_actualizacion`: los genera el sistema.
    - `estado`: toda solicitud nace en el estado inicial. Permitir que el
      cliente lo elija habilitaría crear una solicitud ya "completada",
      saltándose el flujo de atención completo. El estado solo se modifica
      después, por el endpoint dedicado y respetando la máquina de estados.

    Un esquema de entrada que omite deliberadamente ciertos campos es una forma
    de validación por diseño: lo que no está en el contrato no puede enviarse.
    """

    model_config = ConfigDict(
        # Recorta espacios al inicio/fin de todos los campos de texto ANTES de
        # validar longitudes. Sin esto, un `nombre_solicitante` con valor "   "
        # pasaría una validación de longitud mínima y se guardaría un nombre
        # efectivamente vacío.
        str_strip_whitespace=True,
        # Rechaza campos no declarados en vez de ignorarlos en silencio: si un
        # cliente envía "estatus" por error tipográfico, recibe un 422 que
        # señala el problema, en lugar de que el campo se descarte sin aviso y
        # el cliente crea que se aplicó.
        extra="forbid",
        json_schema_extra={
            "example": {
                "identificador_externo": "SOL-2026-000123",
                "tipo": "soporte_tecnico",
                "nombre_solicitante": "Ana María Restrepo",
                "correo": "ana.restrepo@institucion.edu.co",
                "descripcion": "No puedo acceder al portal académico desde el lunes.",
                "prioridad": "alta",
            }
        },
    )

    identificador_externo: str = Field(
        min_length=1,
        max_length=64,
        description="Código único asignado por el sistema de origen.",
    )
    tipo: TipoSolicitud = Field(description="Categoría de la solicitud.")
    nombre_solicitante: str = Field(min_length=1, max_length=150)
    # EmailStr delega la validación en `email-validator`, que aplica las reglas
    # del RFC en lugar de una expresión regular casera (que inevitablemente
    # rechaza direcciones válidas o acepta inválidas).
    correo: EmailStr = Field(description="Correo válido de contacto.")
    # max_length=4000: sin este límite (encontrado en auditoría), era el único
    # campo de texto del esquema sin cota superior. Un cliente podía enviar una
    # descripción de decenas de MB, que Starlette bufferiza completa en memoria
    # antes de validar — con pocas peticiones concurrentes, agota la memoria
    # del proceso; y en GET /solicitudes, N filas con descripciones así de
    # grandes amplifican una petición trivial en una respuesta de gigabytes.
    descripcion: str = Field(
        min_length=1,
        max_length=4000,
        description="Detalle del requerimiento o incidente.",
    )
    prioridad: Prioridad = Field(description="Nivel de atención requerido.")


class EstadoActualizar(BaseModel):
    """Cuerpo aceptado en PATCH /solicitudes/{id}/estado."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"estado": "en_proceso"}},
    )

    estado: EstadoSolicitud = Field(description="Nuevo estado de la solicitud.")


class SolicitudRespuesta(BaseModel):
    """Representación devuelta por la API para una solicitud."""

    # from_attributes=True permite construir el esquema directamente desde el
    # objeto ORM (`SolicitudRespuesta.model_validate(objeto_solicitud)`) sin
    # convertirlo manualmente a diccionario.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    identificador_externo: str
    tipo: TipoSolicitud
    nombre_solicitante: str
    correo: EmailStr
    descripcion: str
    prioridad: Prioridad
    estado: EstadoSolicitud
    fecha_creacion: datetime
    fecha_actualizacion: datetime


class SolicitudPagina(BaseModel):
    """
    Respuesta paginada de GET /solicitudes.

    Se devuelve un objeto con metadatos en lugar de una lista desnuda por dos
    razones: el cliente necesita `total` para construir una paginación, y un
    objeto raíz permite agregar campos en el futuro sin romper el contrato
    (una lista JSON en la raíz no es extensible sin un cambio incompatible).
    """

    total: int = Field(description="Total de registros que cumplen el filtro.")
    limit: int = Field(description="Tamaño de página solicitado.")
    offset: int = Field(description="Desplazamiento aplicado.")
    items: list[SolicitudRespuesta]
