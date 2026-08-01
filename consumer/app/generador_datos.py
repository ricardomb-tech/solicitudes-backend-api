"""
Generación del lote de solicitudes que el consumidor envía en cada ejecución.

Los valores de catálogo (tipo, prioridad) se repiten aquí como constantes de
texto plano, en vez de importarse del backend. Es una duplicación deliberada:
ver la justificación completa en el ADR de este bloque ("por qué el
consumidor no comparte código de dominio con el backend"). En resumen: son dos
servicios independientes que se integran únicamente por su contrato HTTP
público — igual que lo haría un sistema externo real, que jamás tendría
acceso al código Python interno del backend.
"""
from __future__ import annotations

import uuid

_TIPOS = ["acceso_plataforma", "soporte_tecnico", "academica", "administrativa"]
_PRIORIDADES = ["baja", "media", "alta"]


def generar_lote(cantidad: int) -> list[dict]:
    """
    Genera `cantidad` solicitudes con datos variados, y agrega una solicitud
    adicional que REPITE deliberadamente el identificador externo de la
    primera.

    Por qué un duplicado deliberado y no aleatorio: permite demostrar, en una
    ejecución real de `docker compose up` (sin mocks ni simulaciones), el
    manejo de conflicto (409) exigido por el enunciado — sin depender de que
    dos ejecuciones distintas coincidan por casualidad en el mismo
    identificador. Es una decisión consciente de diseño para que los "logs de
    una ejecución de ejemplo" (entregable del Bloque 6) muestren el caso de
    duplicado sin artificios.
    """
    id_ejecucion = uuid.uuid4().hex[:8]
    lote = [
        {
            "identificador_externo": f"EXT-{id_ejecucion}-{i:03d}",
            "tipo": _TIPOS[i % len(_TIPOS)],
            "nombre_solicitante": f"Usuario Externo {i}",
            "correo": f"usuario{i}@sistema-externo.example.com",
            "descripcion": (
                f"Solicitud generada automáticamente por el consumidor "
                f"(lote {id_ejecucion}, ítem {i})."
            ),
            "prioridad": _PRIORIDADES[i % len(_PRIORIDADES)],
        }
        for i in range(cantidad)
    ]

    if lote:
        duplicado = {
            **lote[0],
            "nombre_solicitante": "Usuario Duplicado (demostración de conflicto)",
            "correo": "duplicado@sistema-externo.example.com",
        }
        lote.append(duplicado)

    return lote
