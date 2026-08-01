# ADR-0009: Logs estructurados JSON con identificador de correlación propagado

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 3

## Contexto

El enunciado exige que cada registro de log incluya fecha, nivel, nombre del
servicio, identificador de correlación, método, endpoint, código de respuesta,
tiempo de ejecución y —en el consumidor— número de intento y detalle del error.
Señala además que "se valorará el uso de logs estructurados en formato JSON", y
que los logs deben quedar disponibles vía `docker compose logs -f` **y**
persistirse.

En la propuesta de AWS se exige adicionalmente que "los logs estén
centralizados y las solicitudes sean trazables".

## Decisión

**1. Formato JSON** mediante `structlog`, integrado con el módulo `logging`
estándar de la biblioteca (no usado de forma aislada), para que los registros
de Uvicorn y SQLAlchemy —que usan `logging` estándar— salgan también en JSON.

**2. Identificador de correlación propagado, no solo generado.** El middleware
reutiliza la cabecera `X-Correlation-ID` si viene en la petición, y solo genera
una nueva cuando no viene. Se devuelve siempre en la respuesta.

**3. Ligado al contexto con `contextvars`** (`structlog.contextvars`), de modo
que cualquier log emitido durante la petición lo incluye automáticamente sin
pasarlo como parámetro por la cadena de llamadas.

**4. Doble salida:** `stdout` (contrato con el orquestador, principio
12-factor) y archivo con `RotatingFileHandler` (10 MB × 5) en un volumen. El
fallo al escribir el archivo no es crítico: se avisa y se continúa con stdout.

**5. Medición de duración con `time.perf_counter()`** (reloj monótono).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Logs en texto plano con formato legible | Extraer "todas las peticiones que tardaron más de 500 ms" exige expresiones regulares frágiles. Con JSON cada campo es consultable directamente por CloudWatch Logs Insights, Loki o Elasticsearch, sin parseo. |
| Generar siempre un identificador nuevo en cada servicio | Cada servicio tendría su propia historia y no habría forma de unir las trazas de una misma operación que atraviesa varios servicios — que es justamente lo que exige el requisito de trazabilidad. |
| Variable global para el identificador de correlación | Dos peticiones concurrentes se pisarían el valor entre sí y los logs quedarían cruzados. `contextvars` mantiene un valor por contexto de ejecución, seguro tanto entre corrutinas como entre hilos del threadpool. |
| Pasar el identificador como parámetro a cada función | Contamina la firma de toda la aplicación con un argumento que no tiene nada que ver con la lógica de negocio. |
| `structlog` de forma aislada, sin integrar con `logging` | El flujo de salida mezclaría líneas JSON (de la aplicación) con líneas de texto plano (de Uvicorn y SQLAlchemy), y ningún recolector podría procesarlo de forma uniforme. |
| Archivo de log sin rotación | Un servicio de larga duración termina llenando el disco. Fallo operativo clásico. |
| Solo archivo, sin stdout | `docker compose logs -f` no mostraría nada, incumpliendo un requisito explícito; y en AWS el driver de logs de ECS no recogería nada hacia CloudWatch. |
| `time.time()` para medir duración | Es un reloj de pared: puede ser ajustado por NTP durante la medición y producir duraciones negativas o incorrectas. Para intervalos siempre se usa un reloj monótono. |

## Consecuencias

**A favor:**
- Una única línea de log por petición, autosuficiente, con todos los campos
  exigidos:
  ```json
  {"method":"GET","path":"/solicitudes","status":200,"duration_ms":272.47,
   "event":"peticion_completada","correlation_id":"mi-trace-externo-12345",
   "level":"info","service":"solicitudes-api","timestamp":"2026-08-01T02:19:23.734991Z"}
  ```
- Efecto verificado y no previsto inicialmente: el `correlation_id` aparece
  también en los registros de `uvicorn.access`, sin haber configurado nada
  específico en Uvicorn, porque sus registros pasan por el mismo logger raíz.
- El identificador devuelto en la respuesta permite a un usuario citarlo al
  reportar un problema, y al equipo encontrar la traza exacta — es la pieza que
  hace compatible "no exponer detalles técnicos" (ADR-0008) con "poder
  diagnosticar".
- Traslada directamente a AWS: el mismo formato JSON lo ingiere CloudWatch sin
  transformación, y el `correlation_id` sirve de identificador de traza para
  X-Ray/OpenTelemetry.

**Costo asumido:**
- Los logs JSON son menos legibles a simple vista en desarrollo que un formato
  de texto coloreado. Se acepta porque el destino real de estos logs es un
  sistema de agregación, no un ojo humano leyendo un terminal; para desarrollo
  local puede filtrarse con `jq` si hiciera falta.
- `BaseHTTPMiddleware` de Starlette añade una pequeña sobrecarga por petición
  frente a un middleware ASGI puro. A esta escala es despreciable y se prefiere
  la legibilidad del código.
