# ADR-0013: Clasificación transitorio/definitivo y backoff exponencial con jitter

- **Estado:** Aceptado
- **Fecha:** 2026-08-01
- **Bloque:** 5

## Contexto

El enunciado exige que el consumidor "configure timeout y número máximo de
reintentos", "reintente errores temporales, como errores de conexión o
respuestas 5xx", "no reintente errores definitivos, como respuestas 4xx", y
"continúe su ejecución cuando una solicitud falle". Hay que decidir la
taxonomía exacta de qué se reintenta, cuánto se espera entre reintentos, y
qué hacer con los casos límite que la taxonomía "4xx vs 5xx" no cubre bien.

## Decisión

**1. La taxonomía real no es "4xx vs 5xx" sino "transitorio vs. definitivo":**

| Categoría | Casos | Se reintenta |
|---|---|---|
| Transitorio | Errores de conexión/timeout (`httpx.ConnectError`, `httpx.TimeoutException`, `httpx.NetworkError`), cualquier 5xx, **429** | Sí |
| Definitivo | Cualquier 4xx que no sea 429 (400, 404, 409, 422...) | No |

`429 Too Many Requests` es formalmente un 4xx, pero semánticamente significa
"tu petición está bien, pero ahora no puedo atenderla" — es la excepción
explícita a la regla superficial "4xx no se reintenta", y se documenta como
tal.

**2. Backoff exponencial con jitter completo:**
`espera = random_uniforme(0, base * 2^(intento-1))`, con `base` configurable
(`CONSUMER_BACKOFF_BASE_S`, default 0.5s).

**3. Se respeta la cabecera `Retry-After`** cuando el servidor la envía (en
vez del backoff calculado localmente), soportando la forma numérica en
segundos.

**4. Máximo de intentos totales = 1 (intento inicial) + `CONSUMER_MAX_RETRIES`**
(default 3, es decir 4 intentos totales).

**5. Timeouts separados por fase de la conexión** (`connect` corto, `read`
más permisivo), configurables independientemente.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Tratar 429 como error definitivo (siguiendo la letra literal "4xx no se reintenta") | Ignora la semántica real del código: un 429 dice explícitamente "vuelve a intentar más tarde". Tratarlo como definitivo desperdiciaría información que el propio protocolo HTTP ofrece para coordinar el ritmo de reintento. |
| Backoff exponencial SIN jitter (`espera = base * 2^intento`, determinista) | Si varios clientes fallan al mismo tiempo (por ejemplo, todos porque el servidor se reinició), todos reintentarían exactamente en el mismo instante futuro, sincronizando una nueva oleada de carga sobre un servidor que recién se está recuperando — el patrón conocido como "thundering herd". El jitter distribuye los reintentos en una ventana en vez de un punto. |
| Backoff lineal o constante (esperar siempre lo mismo) | No da tiempo creciente de recuperación a un servidor sobrecargado; el cuarto reintento golpearía con la misma urgencia que el primero, cuando la situación amerita justamente lo contrario. |
| Un único timeout total en vez de timeouts por fase | Un timeout único no distingue "el servidor nunca respondió" (indica que probablemente está caído — se detecta rápido con un timeout de conexión corto) de "el servidor está procesando algo que tarda" (se tolera con un timeout de lectura más permisivo). Fusionarlos obligaría a elegir un valor de compromiso peor para ambos casos. |
| Ignorar `Retry-After` y usar siempre el backoff local | El servidor puede tener información directa que el cliente no tiene (por ejemplo, cuánto durará una ventana de limitación de tasa). Ignorar esa señal desperdicia la coordinación que el propio protocolo ofrece. |

## Consecuencias

**A favor:**
- Verificado con pruebas automatizadas deterministas (`consumer/tests/test_retry.py`,
  usando `httpx.MockTransport`): un 4xx real se falla al primer intento sin
  reintentar; un 5xx o un error de conexión se reintenta hasta 4 veces antes
  de rendirse; un 429 con `Retry-After: 7` espera exactamente 7 segundos, no
  el backoff calculado.
- El `correlation_id` es el mismo en todos los intentos de una misma
  operación lógica (verificado en `test_correlation_id_es_el_mismo_en_todos_los_intentos`),
  lo que permite agrupar los N intentos en los logs bajo un solo identificador.
- El comportamiento de reintento se prueba sin depender de que un servidor
  real falle en el instante exacto que el test necesita — determinista y
  rápido (los tiempos de espera reales se sustituyen por un no-op en las
  pruebas, ver `consumer/tests/conftest.py`).

**Costo asumido:**
- Solo se soporta `Retry-After` en su forma numérica (segundos), no la
  variante de fecha HTTP (`Retry-After: Wed, 21 Oct 2026 07:28:00 GMT`).
  Cubrir ambas formas no aporta valor proporcional al esfuerzo para el
  alcance de este proyecto; sería la primera extensión a considerar en un
  contexto real de integración con APIs de terceros que sí usen esa variante.
