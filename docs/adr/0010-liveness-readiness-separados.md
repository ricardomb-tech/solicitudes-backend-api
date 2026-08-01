# ADR-0010: Endpoints de liveness y readiness separados

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 3

## Contexto

El enunciado pide dos endpoints de salud distintos: `GET /health` ("verificar
disponibilidad de la API") y `GET /health/ready` ("verificar conexión con
PostgreSQL"). Hay que decidir qué comprueba exactamente cada uno — en
particular, si el chequeo de vida debe o no tocar la base de datos.

La distinción no es cosmética: los orquestadores (Docker Compose, ECS,
Kubernetes) reaccionan de forma **diferente** ante el fallo de cada tipo de
chequeo.

## Decisión

| Endpoint | Pregunta que responde | ¿Consulta PostgreSQL? | Reacción del orquestador ante fallo |
|---|---|---|---|
| `GET /health` | ¿El proceso está vivo y puede responder HTTP? | **No** | Reinicia el contenedor |
| `GET /health/ready` | ¿Puedo atender tráfico ahora mismo? | **Sí** (`SELECT 1`) | Saca de rotación sin matar el contenedor |

`/health/ready` devuelve **503 Service Unavailable** (no 500) cuando la
dependencia no responde, y el detalle técnico del fallo va al log, nunca al
cuerpo de la respuesta.

Se ejecuta `SELECT 1` y no una consulta sobre una tabla del negocio: el chequeo
debe verificar **conectividad** (pool → red → servidor → respuesta), no depender
de que exista determinado dato.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Un solo endpoint de salud que verifique todo, incluida la base de datos | Es el error de diseño que esta decisión evita: si el chequeo de **vida** dependiera de PostgreSQL, una caída temporal de la base de datos haría que el orquestador considerara "muertos" a contenedores perfectamente sanos y los reiniciara en bucle — **agravando el incidente en lugar de mitigarlo**. El proceso está bien; lo que falla es una dependencia. |
| `/health/ready` devolviendo 500 en vez de 503 | 500 significa "fallé procesando tu petición". 503 significa "existo, pero no puedo atender ahora" — que es exactamente la situación, y es el código que los balanceadores interpretan como "saca este destino de rotación". |
| Incluir el mensaje de la excepción de conexión en la respuesta de `/health/ready` | Un endpoint de salud suele ser accesible con menos restricciones que el resto de la API; filtrar ahí el host, el puerto o el usuario de la base de datos sería especialmente grave. El detalle va al log (ver ADR-0008). |
| Consultar una tabla del negocio (p. ej. `SELECT count(*) FROM solicitudes`) | Acopla la salud del servicio a la existencia de datos y es innecesariamente costoso en una tabla grande. La conectividad es lo que se quiere verificar. |

## Consecuencias

**A favor:**
- Verificado empíricamente deteniendo el contenedor de PostgreSQL:
  `/health/ready` → **503** `{"status":"degraded","dependencias":{"postgresql":"no_disponible"}}`
  mientras `/health` → **200** `{"status":"ok"}`. El contenedor no se reinicia,
  y vuelve a estar listo automáticamente cuando la base de datos se recupera.
- Conecta directamente con la propuesta de AWS: el *health check* del *target
  group* del ALB apunta a `/health/ready`, de modo que el balanceador retira una
  tarea que perdió la conexión a RDS sin destruirla, dándole oportunidad de
  recuperarse.
- `docker-compose.yml` puede usar `/health` como healthcheck del contenedor y el
  consumidor puede esperar a `/health/ready` antes de empezar a enviar
  peticiones (Bloque 5).

**Costo asumido:**
- Dos endpoints en lugar de uno, y la necesidad de explicar la diferencia a
  quien configure el despliegue. Apuntar el chequeo equivocado al endpoint
  equivocado anula el beneficio, así que la distinción está documentada tanto en
  el código como aquí.
