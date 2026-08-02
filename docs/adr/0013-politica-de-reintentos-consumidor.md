# ADR-0013: Clasificación transitorio/definitivo y backoff exponencial con jitter

- **Estado:** Aceptado
- **Fecha:** 2026-08-01
- **Bloque:** 5

> **En pocas palabras:** no todos los errores merecen el mismo trato. Un `503` (servidor sobrecargado) puede resolverse en segundos; un `400` (petición malformada) no mejorará por más que se reintente. La política separa los errores en dos categorías, espera cada vez más entre reintentos (backoff exponencial) y añade variación aleatoria (jitter) para que varios clientes no se pilen al mismo tiempo sobre un servidor que se está recuperando.

## Contexto

El enunciado exige que el consumidor "configure timeout y número máximo de reintentos", "reintente errores temporales como errores de conexión o respuestas 5xx", "no reintente errores definitivos como respuestas 4xx" y "continúe su ejecución cuando una solicitud falle". Hay que decidir la taxonomía exacta de qué se reintenta, cuánto se espera entre reintentos, y qué hacer con los casos límite que la regla superficial "4xx vs 5xx" no cubre bien.

## Decisión

**1. La taxonomía real es "transitorio vs. definitivo", no "4xx vs 5xx":**

| Categoría | Casos | Se reintenta |
|---|---|---|
| Transitorio | Errores de conexión/timeout, cualquier 5xx, **429** | Sí |
| Definitivo | Cualquier 4xx que no sea 429 (400, 404, 409, 422...) | No |

`429 Too Many Requests` es formalmente un 4xx, pero semánticamente significa "tu petición está bien, solo no puedo atenderla ahora" — es la excepción explícita a la regla "4xx no se reintenta", y el propio protocolo la marca así para coordinar el ritmo del cliente.

**2. Backoff exponencial con jitter completo:**
`espera = random_uniforme(0, base × 2^(intento−1))`, con `base` configurable (`CONSUMER_BACKOFF_BASE_S`, por defecto 0.5 s).

**3. Se respeta la cabecera `Retry-After`** cuando el servidor la envía, usando ese valor en lugar del backoff calculado localmente.

**4. Total de intentos = 1 (inicial) + `CONSUMER_MAX_RETRIES`** (por defecto 3 — es decir, 4 intentos totales).

**5. Timeouts separados por fase:** `connect` corto (detectar rápido si el servidor está caído), `read` más permisivo (tolerar respuestas lentas sin considerarlas un timeout de conexión).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Tratar `429` como error definitivo (interpretación literal de "4xx no se reintenta") | Ignora la semántica real del código: un `429` dice explícitamente "vuelve a intentar más tarde". Tratarlo como definitivo desperdiciaría la coordinación que el propio protocolo ofrece. |
| Backoff exponencial SIN jitter (`espera = base × 2^intento`, determinista) | Si varios clientes fallan al mismo tiempo, todos reintentarían exactamente en el mismo instante futuro — una nueva oleada de carga sincronizada sobre un servidor que recién se está recuperando. Es el patrón conocido como "thundering herd". El jitter distribuye los reintentos en una ventana de tiempo en lugar de un único punto. |
| Backoff lineal o constante | No da tiempo creciente de recuperación a un servidor sobrecargado. El cuarto reintento golpearía con la misma urgencia que el primero, cuando la situación pide justamente lo contrario. |
| Un único timeout total en vez de timeouts por fase | No distingue "el servidor nunca respondió" (se detecta rápido con un timeout de conexión corto) de "el servidor está procesando algo que tarda" (se tolera con un timeout de lectura más permisivo). Un valor único obliga a elegir un compromiso peor para ambos casos. |
| Ignorar `Retry-After` y usar siempre el backoff local | El servidor puede saber mejor que el cliente cuánto durará una ventana de limitación de tasa. Ignorar esa señal desperdicia información que el protocolo ofrece para coordinar exactamente esta situación. |

## Consecuencias

**Lo que se gana:**
- Verificado con pruebas deterministas (`consumer/tests/test_retry.py`, usando `httpx.MockTransport`): un `4xx` real se falla al primer intento sin reintentar; un `5xx` o error de conexión se reintenta hasta 4 veces; un `429` con `Retry-After: 7` espera exactamente 7 segundos, no el backoff calculado.
- El `correlation_id` es el mismo en todos los intentos de una misma operación lógica, lo que permite agrupar los N reintentos en los logs bajo un solo identificador.
- El comportamiento de reintento se prueba sin depender de que un servidor real falle en el momento exacto que el test necesita — los tiempos de espera reales se sustituyen por un no-op en las pruebas.

**Lo que se paga:**
- Solo se soporta `Retry-After` en su forma numérica (segundos), no la variante de fecha HTTP (`Retry-After: Wed, 21 Oct 2026 07:28:00 GMT`). Cubrir ambas formas no aporta valor proporcional al esfuerzo para el alcance de este proyecto; sería la primera extensión a considerar en una integración con APIs de terceros que usen esa variante.
