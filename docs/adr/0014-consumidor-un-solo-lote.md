# ADR-0014: El consumidor procesa un solo lote y termina (no es un bucle continuo)

- **Estado:** Aceptado
- **Fecha:** 2026-08-01
- **Bloque:** 5

## Contexto

El enunciado pide "un servicio consumidor que simule un sistema externo",
que "envíe varias solicitudes", "consulte posteriormente su estado" y
"registre el resultado de cada petición". No especifica si debe ejecutarse
una vez o de forma periódica/continua. Hay que decidir el ciclo de vida del
proceso y, en consecuencia, la política de reinicio (`restart:`) del
contenedor en `docker-compose.yml`.

## Decisión

El consumidor ejecuta **un solo lote** de principio a fin (genera las
solicitudes, las envía con su política de reintentos, consulta el estado de
las creadas, registra un resumen) y **termina con código de salida 0**. En
`docker-compose.yml` se declara `restart: "no"` explícitamente.

El healthcheck del `backend` (ver el propio `docker-compose.yml`) permite que
`consumer` declare `depends_on: backend: condition: service_healthy`,
apuntando a `/health/ready` — el consumidor no empieza a enviar tráfico hasta
que el backend puede realmente atenderlo (BD incluida), no solo hasta que el
proceso de Uvicorn arrancó.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Bucle infinito que envía un lote cada N segundos, indefinidamente | Simularía más fielmente un sistema externo real con tráfico continuo, pero generaría logs y datos crecientes sin límite en cada `docker compose up` de desarrollo o evaluación, dificultando revisar "una ejecución de ejemplo" (el entregable pedido en la sección 4 del enunciado) — sería necesario decidir arbitrariamente cuándo cortar la captura de logs. Un lote único y determinista produce un resultado acotado y reproducible. |
| `restart: unless-stopped` (el mismo valor usado en `backend` y `db`) con el proceso actual (un solo lote) | Como el proceso termina con código 0 al completar su lote, `unless-stopped` haría que Compose lo reiniciara indefinidamente, ejecutando el lote una y otra vez en bucle — un comportamiento no evidente a partir de la configuración (parecería un bucle continuo "por accidente" en vez de una decisión explícita). Se prefiere que el ciclo de vida sea el que el código expresa literalmente: una ejecución, un resultado, fin. |
| Exponer el consumidor como un servicio HTTP con un endpoint "disparar lote" | Añade complejidad (sería necesario un servidor HTTP, una ruta, autenticación mínima) para un componente cuyo único propósito es demostrar el patrón de integración saliente; no aporta valor frente al enunciado, que no pide que el consumidor sea invocable bajo demanda por otros sistemas. |

## Consecuencias

**A favor:**
- Cada `docker compose up --build` (o `docker compose run --rm consumer`)
  produce una ejecución completa, acotada y con un resumen final claro en los
  logs — exactamente lo que se necesita para el entregable "logs de una
  ejecución de ejemplo".
- El comportamiento es predecible: quien lea `docker-compose.yml` ve
  `restart: "no"` y entiende de inmediato que es un proceso de un solo lote,
  sin necesidad de inferir esa intención a partir de que el código simplemente
  termina.
- Para simular una integración periódica real, basta con invocar
  `docker compose run --rm consumer` cuantas veces se necesite, o
  —en un entorno real— programarlo con un *scheduler* externo (cron, EventBridge
  Scheduler en AWS), que es además el patrón estándar para este tipo de tarea
  por lotes en la nube, y se referencia en la propuesta de AWS.

**Costo asumido:**
- No demuestra, dentro de una sola ejecución de `docker compose up`, un
  patrón de tráfico continuo o sostenido en el tiempo. Se considera un costo
  aceptable: el enunciado pide demostrar el *patrón* de reintentos y manejo de
  errores (ya cubierto exhaustivamente con pruebas automatizadas, ver
  ADR-0013), no un generador de carga sostenida.
