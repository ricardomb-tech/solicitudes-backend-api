# ADR-0009: Logs estructurados JSON con identificador de correlación propagado

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 3

> **En pocas palabras:** cada línea de log es un JSON con campos nombrados, no texto libre. El `correlation_id` de la petición está en todos los campos, propagado automáticamente sin pasarlo como parámetro. Así se puede filtrar "todo lo que ocurrió durante esta petición" con una sola consulta, y el cliente puede reportar un error citando solo ese ID.

## Contexto

El enunciado exige que cada registro de log incluya fecha, nivel, nombre del servicio, identificador de correlación, método, endpoint, código de respuesta, tiempo de ejecución y — en el consumidor — número de intento y detalle del error. También indica que "se valorará el uso de logs estructurados en formato JSON" y que los logs deben estar disponibles vía `docker compose logs -f` y persistirse.

La propuesta de AWS exige además que "los logs estén centralizados y las solicitudes sean trazables".

## Decisión

**1. Formato JSON** mediante `structlog`, integrado con el módulo `logging` estándar de Python para que los registros de Uvicorn y SQLAlchemy — que usan `logging` estándar — salgan también en JSON, no como líneas de texto plano mezcladas con el JSON de la aplicación.

**2. `correlation_id` propagado, no solo generado.** El middleware reutiliza la cabecera `X-Correlation-ID` si viene en la petición de entrada, y solo genera uno nuevo cuando no viene. Siempre se devuelve en la respuesta. Esto permite rastrear una operación que atraviesa varios servicios bajo un mismo identificador.

**3. Ligado al contexto con `contextvars`** (`structlog.contextvars`), de modo que cualquier log emitido durante la petición incluye automáticamente el `correlation_id` sin pasarlo como parámetro a través de toda la cadena de llamadas.

**4. Doble salida:** `stdout` (contrato con el orquestador, principio 12-factor) y archivo con `RotatingFileHandler` (10 MB × 5 archivos) en un volumen. Si falla la escritura en archivo, se avisa en `stdout` y se continúa — el log no es crítico para el servicio.

**5. Duración con `time.perf_counter()`** — reloj monótono, no reloj de pared.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Logs en texto plano con formato legible | Extraer "todas las peticiones que tardaron más de 500 ms" requiere expresiones regulares frágiles. Con JSON cada campo es consultable directamente por CloudWatch Logs Insights, Loki o Elasticsearch, sin parseo. |
| Generar siempre un `correlation_id` nuevo en cada servicio, sin propagarlo | Cada servicio tiene su propia historia y no hay forma de unir las trazas de una misma operación. La trazabilidad que exige el enunciado se pierde. |
| Variable global para el `correlation_id` | Dos peticiones concurrentes se pisarían el valor mutuamente y los logs quedarían cruzados. `contextvars` mantiene un valor por contexto de ejecución, seguro tanto en corrutinas como en hilos del threadpool. |
| Pasar el `correlation_id` como parámetro a cada función | Contamina la firma de toda la aplicación con un argumento que no tiene nada que ver con la lógica de negocio. Si se añade una capa nueva, hay que actualizar todas las firmas intermedias. |
| `structlog` sin integrar con `logging` estándar | La salida mezclaría líneas JSON (de la aplicación) con líneas de texto plano (de Uvicorn y SQLAlchemy), y ningún recolector podría procesarlas de forma uniforme. |
| Archivo de log sin rotación | Un servicio de larga duración termina llenando el disco. Fallo operativo clásico y evitable. |
| Solo archivo, sin `stdout` | `docker compose logs -f` no mostraría nada, incumpliendo un requisito explícito. En AWS, el driver de logs de ECS recoge desde `stdout` — sin esa salida, CloudWatch no recibiría nada. |
| `time.time()` para medir duración | Es un reloj de pared ajustable por NTP: puede producir duraciones negativas o incorrectas si NTP sincroniza durante la medición. Para intervalos siempre se usa un reloj monótono. |

## Consecuencias

**Lo que se gana:**
- Una sola línea de log por petición, autosuficiente, con todos los campos exigidos:
  ```json
  {"method":"GET","path":"/solicitudes","status":200,"duration_ms":272.47,
   "event":"peticion_completada","correlation_id":"mi-trace-externo-12345",
   "level":"info","service":"solicitudes-api","timestamp":"2026-08-01T02:19:23.734991Z"}
  ```
- Efecto no previsto pero verificado: el `correlation_id` aparece también en los registros de `uvicorn.access`, sin haber configurado nada específico en Uvicorn, porque sus registros pasan por el mismo logger raíz.
- El `correlation_id` devuelto en la respuesta permite que un usuario lo cite al reportar un problema, y al equipo encontrar la traza exacta — es la pieza que hace compatible "no exponer detalles técnicos" (ADR-0008) con "poder diagnosticar".
- El mismo formato JSON es ingerido directamente por CloudWatch sin transformación. El `correlation_id` sirve de identificador de traza para X-Ray u OpenTelemetry en la propuesta de AWS.

**Lo que se paga:**
- Los logs JSON son menos legibles a simple vista en un terminal que un formato de texto coloreado. El destino real de estos logs es un sistema de agregación; para desarrollo local se puede filtrar con `jq`.
- `BaseHTTPMiddleware` de Starlette añade una pequeña sobrecarga por petición frente a un middleware ASGI puro. A esta escala es despreciable y se prefiere la legibilidad del código.
