# ADR-0005: Healthcheck de Postgres + `depends_on: condition: service_healthy`

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 1 — implementado y verificado

## Contexto

El enunciado exige "health checks y control del orden de inicialización". En
Docker Compose, `depends_on` sin condición solo garantiza que Docker *inicie*
el contenedor dependido antes que el dependiente — no que el proceso interno
ya esté listo para aceptar trabajo. PostgreSQL, en particular, tarda algunos
segundos en aceptar conexiones después de que su contenedor "arrancó" (init de
archivos de datos, `pg_ctl start` interno). Sin un mecanismo adicional, el
backend intentaría conectarse antes de que Postgres esté listo y fallaría en
todo arranque en frío.

## Decisión

- El servicio `db` declara un `healthcheck` usando `pg_isready` (el comando
  oficial de PostgreSQL para verificar que el servidor acepta conexiones),
  con `interval`, `timeout`, `retries` y `start_period` explícitos.
- El servicio `backend` declara `depends_on: db: condition: service_healthy`,
  no `depends_on: db` a secas.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `depends_on` simple (sin condición) | No resuelve el problema descrito; es la causa más común de fallos en el primer arranque de proyectos con Compose. |
| Script de espera externo (`wait-for-it.sh`, `dockerize -wait`) en el `entrypoint` del backend | Añade una dependencia externa y un script adicional para resolver algo que Compose ya soporta de forma nativa desde la versión 3 del *file format* (`condition: service_healthy`). Se prefiere la solución nativa por simplicidad. |
| Reintentos de conexión dentro del propio código de la aplicación al arrancar, sin healthcheck de Compose | Es una defensa adicional razonable (y de hecho se recomienda igual para el entorno de AWS, donde no existe un `depends_on` de Compose), pero no sustituye el control de orden a nivel de orquestador local: sin healthcheck, el contenedor de backend se reiniciaría en bucle (`restart: unless-stopped`) hasta que Postgres esté listo, generando ruido en los logs que un healthcheck evita directamente. |

## Consecuencias

**A favor:**
- El arranque en frío (`docker compose down -v && docker compose up --build`)
  es determinístico: el backend siempre arranca después de que `db` reporta
  `healthy`, verificado empíricamente inspeccionando `docker compose logs`
  en un arranque en frío (el orden `db Healthy` → `backend Starting` es
  visible directamente en la salida de Compose).
- El mismo patrón (`healthcheck` + `condition: service_healthy`) se reutiliza
  para que el servicio `consumer` espere a que `backend` esté listo antes de
  empezar a enviar peticiones (ver `docker-compose.yml`).

**Costo asumido:**
- Un arranque en frío tarda algunos segundos más (`start_period` +
  `interval` de gracia) que si no hubiera healthcheck. Es un costo trivial
  frente a evitar fallos de conexión intermitentes.
