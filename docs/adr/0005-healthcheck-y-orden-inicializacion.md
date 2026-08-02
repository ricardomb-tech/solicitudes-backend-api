# ADR-0005: Healthcheck de Postgres + `depends_on: condition: service_healthy`

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 1 — implementado y verificado

> **En pocas palabras:** Docker Compose no sabe si Postgres ya está listo para aceptar conexiones, solo sabe si el contenedor "arrancó". Con un `healthcheck` y `condition: service_healthy`, el backend espera a que Postgres responda de verdad, no a que su contenedor simplemente exista.

## Contexto

El enunciado exige "health checks y control del orden de inicialización". En Docker Compose, `depends_on` sin condición solo garantiza que Docker *inicie* el contenedor dependido antes que el dependiente — no que el proceso interno ya esté listo para aceptar trabajo. PostgreSQL tarda varios segundos después de que su contenedor "arrancó" en estar listo para aceptar conexiones (inicializa archivos de datos, levanta `pg_ctl`). Sin un mecanismo adicional, el backend intentaría conectarse antes de que Postgres esté listo y fallaría en cada arranque en frío, requiriendo reiniciar el contenedor a mano.

## Decisión

- El servicio `db` declara un `healthcheck` usando `pg_isready` (el comando oficial de PostgreSQL para verificar que el servidor acepta conexiones), con `interval`, `timeout`, `retries` y `start_period` explícitos.
- El servicio `backend` declara `depends_on: db: condition: service_healthy`, no `depends_on: db` a secas.

El mismo patrón se aplica en cascada: `consumer` declara `depends_on: backend: condition: service_healthy`, de modo que el consumidor no empieza a enviar peticiones hasta que el backend pueda realmente atenderlas (base de datos incluida).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| `depends_on` simple, sin condición | Es la causa más común de fallos en el primer arranque de proyectos con Compose. Solo garantiza orden de inicio del contenedor, no que el proceso esté listo. El backend arrancaría, intentaría conectarse a Postgres, fallaría, y se necesitaría reiniciar a mano. |
| Script de espera externo (`wait-for-it.sh`, `dockerize`) en el entrypoint del backend | Añade una dependencia externa y un script adicional para resolver algo que Compose ya soporta de forma nativa desde la versión 3 del formato de archivo con `condition: service_healthy`. Siempre es preferible la solución nativa sobre añadir una dependencia nueva. |
| Reintentos de conexión dentro del código de la aplicación, sin healthcheck de Compose | Es una defensa adicional razonable —y de hecho recomendada en entornos como AWS donde no existe `depends_on`— pero no sustituye el control de orden a nivel de orquestador local. Sin healthcheck, el contenedor de backend se reiniciaría en bucle hasta que Postgres esté listo, generando ruido en los logs que el healthcheck evita directamente. |

## Consecuencias

**Lo que se gana:**
- El arranque en frío (`docker compose down -v && docker compose up --build`) es determinístico. El orden `db Healthy → backend Starting` es visible directamente en la salida de `docker compose logs` — verificable por cualquiera que clone el repositorio.
- El patrón se reutiliza dos veces en el mismo `docker-compose.yml` (`backend` espera a `db`; `consumer` espera a `backend`), lo que garantiza que toda la cadena de dependencias respeta el mismo criterio de "listo de verdad".

**Lo que se paga:**
- Un arranque en frío tarda algunos segundos más (el `start_period` y el `interval` de gracia del healthcheck) que si no hubiera healthcheck. Es un costo trivial frente a evitar fallos de conexión intermitentes.
