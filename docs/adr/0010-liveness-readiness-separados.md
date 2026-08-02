# ADR-0010: Endpoints de liveness y readiness separados

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 3

> **En pocas palabras:** `/health` responde si el proceso está vivo (sin tocar la base de datos). `/health/ready` responde si puede atender tráfico ahora mismo (con un `SELECT 1` a Postgres). La distinción importa porque el orquestador reacciona de forma diferente al fallo de cada uno: al primero reinicia el contenedor, al segundo lo saca de rotación sin matarlo.

## Contexto

El enunciado pide dos endpoints de salud distintos: `GET /health` ("verificar disponibilidad de la API") y `GET /health/ready` ("verificar conexión con PostgreSQL"). Hay que decidir qué comprueba exactamente cada uno — en particular, si el chequeo de vida debe o no tocar la base de datos.

La distinción no es cosmética. Los orquestadores (Docker Compose, ECS, Kubernetes) reaccionan de forma **diferente** ante el fallo de cada tipo de chequeo, y mezclarlos produce consecuencias reales durante incidentes.

## Decisión

| Endpoint | Pregunta que responde | ¿Consulta PostgreSQL? | Reacción del orquestador ante fallo |
|---|---|---|---|
| `GET /health` | ¿El proceso está vivo y puede responder HTTP? | **No** | Reinicia el contenedor |
| `GET /health/ready` | ¿Puedo atender tráfico ahora mismo? | **Sí** (`SELECT 1`) | Saca de rotación sin matar el contenedor |

`/health/ready` devuelve **503 Service Unavailable** (no 500) cuando Postgres no responde. El detalle técnico del error va al log, nunca al cuerpo de la respuesta. Se usa `SELECT 1` y no una consulta de negocio: lo que se quiere verificar es conectividad (pool → red → servidor → respuesta), no que existan datos.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Un solo endpoint de salud que verifique todo, incluida la base de datos | Es el error de diseño que esta decisión evita. Si el chequeo de *vida* dependiera de Postgres, una caída temporal de la base de datos haría que el orquestador considerara "muertos" a contenedores perfectamente sanos y los reiniciara en bucle — **agravando el incidente en lugar de mitigarlo**. El proceso del backend está bien; lo que falla es una dependencia. |
| `/health/ready` devolviendo `500` en vez de `503` | `500` significa "fallé procesando tu petición". `503` significa "existo, pero no puedo atender ahora" — que es exactamente la situación. Los balanceadores de carga interpretan `503` como "saca este destino de rotación"; `500` puede interpretarse como un error puntual de la petición, no como una señal de no-disponibilidad. |
| Incluir el mensaje de la excepción de conexión en la respuesta de `/health/ready` | Un endpoint de salud suele ser accesible con menos restricciones que el resto de la API. Filtrar ahí el host, el puerto o el usuario de la base de datos sería especialmente grave. El detalle va al log (ver ADR-0008). |
| Consultar una tabla de negocio (`SELECT count(*) FROM solicitudes`) | Acopla la salud del servicio a la existencia de datos y es innecesariamente costoso en una tabla grande. Lo que se quiere verificar es conectividad, no datos. |

## Consecuencias

**Lo que se gana:**
- Verificado empíricamente deteniendo el contenedor de PostgreSQL: `/health/ready` devuelve `503 {"status":"degraded","dependencias":{"postgresql":"no_disponible"}}` mientras `/health` sigue en `200 {"status":"ok"}`. El contenedor no se reinicia, y vuelve automáticamente al estado `healthy` cuando la base de datos se recupera.
- Conecta directamente con la propuesta de AWS: el healthcheck del target group del ALB apunta a `/health/ready`, de modo que el balanceador retira una tarea que perdió la conexión a RDS sin destruirla, dándole oportunidad de recuperarse.
- `docker-compose.yml` usa `/health/ready` como healthcheck del backend, y `consumer` declara `depends_on: backend: condition: service_healthy` sobre ese mismo check — no empieza a enviar peticiones hasta que el backend puede realmente atenderlas.

**Lo que se paga:**
- Dos endpoints en lugar de uno, y la necesidad de explicar la diferencia a quien configure el despliegue. Apuntar el chequeo equivocado al endpoint equivocado anula todo el beneficio — por eso está documentado tanto en el código como aquí.
