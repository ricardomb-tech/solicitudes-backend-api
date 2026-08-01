"""
Política de reintentos del consumidor (REQ-C-04 a REQ-C-06, ADR-0013).

La idea central: no toda respuesta de error amerita el mismo tratamiento.

- TRANSITORIO: el problema es probable que se resuelva solo con el tiempo
  (el servidor estaba sobrecargado, hubo un corte de red momentáneo). Vale la
  pena reintentar la MISMA petición.
- DEFINITIVO: el problema está en la petición misma (datos inválidos, recurso
  inexistente, conflicto de negocio). Reintentar la petición idéntica produce
  exactamente el mismo resultado — es trabajo desperdiciado, y en el peor
  caso, ruido en los logs que dificulta encontrar el problema real.

Esta distinción NO es "5xx vs 4xx" de forma literal: 429 (Too Many Requests)
es formalmente un 4xx pero semánticamente transitorio ("ahora no, intenta más
tarde"), así que se lo trata como tal.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import httpx


@dataclass
class ResultadoPeticion:
    """Resultado final de una petición, después de agotar reintentos o tener éxito."""

    exito: bool
    intentos_realizados: int
    respuesta: httpx.Response | None = None
    error: str | None = None

    @property
    def es_fallo_definitivo(self) -> bool:
        """
        True si el fallo es un 4xx real (no 429): reintentar no habría
        cambiado nada. False si el fallo es por agotar reintentos ante algo
        transitorio (5xx, 429, o error de red/timeout).
        """
        return (
            not self.exito
            and self.respuesta is not None
            and self.respuesta.status_code < 500
            and self.respuesta.status_code != 429
        )


def es_respuesta_transitoria(respuesta: httpx.Response) -> bool:
    """
    5xx (error del servidor) o 429 (límite de tasa) se consideran
    transitorios: ambos son señales de "el servidor no puede atender esto
    AHORA", no "esta petición está mal formada".
    """
    return respuesta.status_code >= 500 or respuesta.status_code == 429


def segundos_de_retry_after(respuesta: httpx.Response) -> float | None:
    """
    Si el servidor envía `Retry-After` (típico en 429 y algunos 503), se
    respeta ese valor en lugar del backoff calculado localmente: el servidor
    tiene información directa de cuándo puede volver a atender que el cliente
    no tiene forma de adivinar. Solo se soporta la forma numérica (segundos),
    no la variante de fecha HTTP — es la forma que usan la gran mayoría de
    APIs REST, y cubrir la variante de fecha no aporta valor proporcional al
    esfuerzo para el alcance de este proyecto.
    """
    valor = respuesta.headers.get("Retry-After")
    if valor is None:
        return None
    try:
        return max(0.0, float(valor))
    except ValueError:
        return None


def calcular_espera(intento: int, base_s: float) -> float:
    """
    Backoff exponencial con "jitter completo" (full jitter):

        espera = random_uniforme(0, base * 2^(intento - 1))

    Por qué EXPONENCIAL: si el servidor está sobrecargado, reintentar de
    inmediato agrega más carga justo cuando menos se necesita. Cada fallo
    sucesivo espera progresivamente más, dando tiempo real de recuperación.

    Por qué JITTER (aleatoriedad) y no un backoff exponencial "limpio": sin
    aleatoriedad, N clientes que fallaron en el mismo instante (por ejemplo,
    todos porque el servidor se reinició) reintentarían TODOS en el mismo
    instante futuro exacto, volviendo a golpear al servidor de forma
    sincronizada — el patrón conocido como "thundering herd" (estampida). El
    jitter distribuye los reintentos en una ventana de tiempo en lugar de
    concentrarlos en un punto.
    """
    techo = base_s * (2 ** (intento - 1))
    return random.uniform(0, techo)
