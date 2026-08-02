# ADR-0014: El consumidor procesa un solo lote y termina (no es un bucle continuo)

- **Estado:** Aceptado
- **Fecha:** 2026-08-01
- **Bloque:** 5

> **En pocas palabras:** el consumidor hace su trabajo (envía el lote, consulta estados, registra el resumen) y termina con código de salida 0. No es un daemon. `docker compose up` muestra una ejecución completa y acotada, no un stream infinito. Para repetirlo basta con `docker compose run --rm consumer`.

## Contexto

El enunciado pide "un servicio consumidor que simule un sistema externo", que "envíe varias solicitudes", "consulte posteriormente su estado" y "registre el resultado de cada petición". No especifica si debe ejecutarse una vez o de forma periódica. Hay que decidir el ciclo de vida del proceso y, en consecuencia, la política de reinicio del contenedor en `docker-compose.yml`.

## Decisión

El consumidor ejecuta **un solo lote** de principio a fin y **termina con código de salida 0**. En `docker-compose.yml` se declara `restart: "no"` explícitamente.

El `depends_on: backend: condition: service_healthy` garantiza que el consumidor no empiece a enviar tráfico hasta que el backend pueda realmente atenderlo (base de datos incluida), no solo hasta que el proceso de Uvicorn arrancó.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Bucle infinito que envía un lote cada N segundos | Simularía más fielmente un sistema externo real con tráfico continuo, pero generaría logs y datos crecientes sin límite en cada `docker compose up`, dificultando revisar "una ejecución de ejemplo" (el entregable pedido en el enunciado). Un lote único y determinista produce un resultado acotado y reproducible. |
| `restart: unless-stopped` (el mismo valor de `backend` y `db`) con el proceso actual | Como el proceso termina con código 0 al completar su lote, `unless-stopped` haría que Compose lo reiniciara indefinidamente, ejecutando el lote en bucle por accidente. El ciclo de vida quedaría determinado por cómo Compose interpreta el código de salida, no por una decisión explícita. Se prefiere que el comportamiento sea lo que el código expresa literalmente. |
| Exponer el consumidor como servicio HTTP con un endpoint "disparar lote" | Añade complejidad (servidor HTTP, ruta, autenticación mínima) para un componente cuyo único propósito es demostrar el patrón de integración saliente. El enunciado no pide que el consumidor sea invocable por otros sistemas. |

## Consecuencias

**Lo que se gana:**
- Cada `docker compose up --build` produce una ejecución completa, acotada y con un resumen final claro en los logs — exactamente lo que se necesita para el entregable "logs de una ejecución de ejemplo".
- El comportamiento es predecible: quien lea `docker-compose.yml` ve `restart: "no"` y entiende de inmediato que es un proceso de un solo lote, sin necesidad de inferirlo a partir del código.
- Para simular una integración periódica, basta con invocar `docker compose run --rm consumer` las veces necesarias, o en un entorno real programarlo con un scheduler externo (cron, EventBridge Scheduler en AWS) — que es además el patrón estándar para tareas por lotes en la nube.

**Lo que se paga:**
- No demuestra un patrón de tráfico continuo dentro de una sola ejecución de `docker compose up`. Se considera aceptable: el enunciado pide demostrar el patrón de reintentos y manejo de errores (cubierto exhaustivamente con pruebas automatizadas, ver ADR-0013), no un generador de carga sostenida.
