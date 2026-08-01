# Arquitectura del sistema

> Convención de esta prueba: se usa la notación **C4** (Contexto → Contenedores
> → Componentes) simplificada, más diagramas de secuencia para los dos flujos
> que concentran la mayor complejidad de negocio (concurrencia en la creación,
> y política de reintentos del consumidor). Cada diagrama indica qué parte ya
> está **implementada** y qué parte es **diseño planeado** para bloques
> siguientes, para que este documento sea honesto sobre el estado real del
> proyecto en cada momento (se actualiza a medida que avanza).

## 1. Diagrama de contexto (C4 – Nivel 1)

Quién usa el sistema y con qué otros sistemas interactúa, sin entrar en
tecnología todavía.

```mermaid
C4Context
    title Contexto — Sistema de Gestión de Solicitudes Institucionales

    Person(usuario, "Solicitante / Usuario institucional", "Crea y consulta solicitudes")
    System(frontend, "Aplicación Frontend", "Ecosistema existente de la organización (fuera del alcance de esta prueba)")
    System(solicitudes, "Servicio de Solicitudes", "API REST — objeto de esta prueba técnica")
    System_Ext(consumidor, "Servicio Consumidor", "Simula un sistema externo que integra con el servicio de solicitudes")
    SystemDb(postgres, "PostgreSQL", "Persistencia de solicitudes")

    Rel(usuario, frontend, "Usa")
    Rel(frontend, solicitudes, "Consume vía HTTPS/REST")
    Rel(consumidor, solicitudes, "Envía y consulta solicitudes vía REST")
    Rel(solicitudes, postgres, "Lee/escribe", "SQL")
```

## 2. Diagrama de contenedores (C4 – Nivel 2) — topología Docker Compose

```mermaid
flowchart TB
    subgraph host["Host Docker — docker compose up --build"]
        subgraph net["Red interna: solicitudes-net (bridge)"]
            backend["backend\nFastAPI + Uvicorn\npuerto 8000\n(estado: implementado, Bloque 1)"]
            db[("db\nPostgreSQL 16-alpine\nvolumen: pgdata\n(estado: implementado, Bloque 1)")]
            consumer["consumer\nservicio simulador (1 lote, restart: no)\n(estado: implementado, Bloque 5)"]
        end
        logs[("volumen: backend-logs\n(estado: implementado, Bloque 1)")]
    end

    cliente["Cliente HTTP\n(Swagger / curl / Postman / Bruno)"]

    cliente -- "8000:8000 (único puerto publicado al host)" --> backend
    backend -- "5432, solo red interna\n(sin ports: expuesto al host)" --> db
    backend -. escribe .-> logs
    consumer -- "http://backend:8000\n(DNS interno de Compose)" --> backend
    consumer -. "depends_on: backend healthy (via /health/ready)" .-> backend
```

**Nota de diseño verificada empíricamente (Bloque 1):** `db` no publica el
puerto 5432 al host — solo es alcanzable desde `backend` dentro de la red
`solicitudes-net`. Es la misma restricción que exige la sección de AWS
("PostgreSQL deberá permanecer en una red privada"), aplicada aquí ya en el
entorno local para que el hábito y el diseño sean uno solo, no dos mundos
distintos.

## 3. Modelo de datos (diagrama entidad-relación) — implementado (Bloque 2)

```mermaid
erDiagram
    SOLICITUDES {
        UUID id PK "Generado por la app/BD, ver ADR-0002"
        VARCHAR identificador_externo UK "Único — ver ADR-0003"
        VARCHAR tipo "CHECK: acceso_plataforma | soporte_tecnico | academica | administrativa"
        VARCHAR nombre_solicitante
        VARCHAR correo
        TEXT descripcion
        VARCHAR prioridad "CHECK: baja | media | alta"
        VARCHAR estado "CHECK: recibida | en_proceso | completada | rechazada — ver máquina de estados"
        TIMESTAMPTZ fecha_creacion "server_default now()"
        TIMESTAMPTZ fecha_actualizacion "onupdate now()"
    }
```

Índices implementados (verificados con `\d solicitudes` en PostgreSQL):
`UNIQUE(identificador_externo)` (integridad + soporte de `ON CONFLICT`);
compuesto `(estado, tipo, prioridad)` (filtro combinado del listado);
`(fecha_creacion DESC)` (orden por defecto).

### Máquina de estados de `estado` (implementada y aplicada — Bloque 3)

```mermaid
stateDiagram-v2
    [*] --> recibida: creación
    recibida --> en_proceso
    en_proceso --> completada
    en_proceso --> rechazada
    recibida --> rechazada
    completada --> [*]
    rechazada --> [*]

    note right of completada
        Estado terminal: cualquier
        transición posterior es
        rechazada con 409.
    end note
    note right of rechazada
        Estado terminal: mismo
        criterio que "completada".
    end note
```

## 4. Diagrama de secuencia — creación concurrente (ADR-0003)

Dos peticiones simultáneas con el **mismo** `identificador_externo`. Este es
el flujo que la prueba pide manejar explícitamente ("solicitudes concurrentes
con el mismo identificador").

```mermaid
sequenceDiagram
    participant C1 as Cliente A
    participant C2 as Cliente B
    participant API as Backend (FastAPI)
    participant DB as PostgreSQL

    par Peticiones simultáneas
        C1->>API: POST /solicitudes (id_externo=X)
    and
        C2->>API: POST /solicitudes (id_externo=X)
    end

    API->>DB: INSERT ... ON CONFLICT (identificador_externo) DO NOTHING RETURNING *
    API->>DB: INSERT ... ON CONFLICT (identificador_externo) DO NOTHING RETURNING *

    Note over DB: El motor serializa las dos escrituras;<br/>solo una obtiene la fila (RETURNING no vacío).

    DB-->>API: fila creada (para la que ganó)
    DB-->>API: 0 filas (para la que perdió)

    API-->>C1: 201 Created (si ganó) / 409 Conflict (si perdió)
    API-->>C2: 201 Created (si ganó) / 409 Conflict (si perdió)

    Note over C1,C2: Exactamente una de las dos recibe 201.<br/>La otra recibe 409, nunca un 500.
```

## 5. Diagrama de secuencia — consumidor con reintentos (implementado, Bloque 5)

```mermaid
sequenceDiagram
    participant Cons as Consumer
    participant API as Backend

    Cons->>API: POST /solicitudes (intento 1)
    API-->>Cons: 503 Service Unavailable

    Note over Cons: 503 es transitorio → reintentar.<br/>Backoff exponencial + jitter.

    Cons->>Cons: espera ~0.5s ± jitter
    Cons->>API: POST /solicitudes (intento 2)
    API-->>Cons: 502 Bad Gateway

    Cons->>Cons: espera ~1s ± jitter
    Cons->>API: POST /solicitudes (intento 3)
    API-->>Cons: 201 Created

    Note over Cons: Éxito. Se registra el resultado<br/>(intentos=3, correlation_id) y continúa<br/>con la siguiente solicitud de su lote.

    Cons->>API: POST /solicitudes (otra solicitud, id_externo duplicado)
    API-->>Cons: 409 Conflict

    Note over Cons: 409 es definitivo → NO se reintenta.<br/>Se registra el fallo y se continúa<br/>(el consumidor nunca aborta el lote completo).
```

## 6. Estado de avance de este documento

| Sección | Estado |
|---|---|
| Contexto | Vigente desde Bloque 0 |
| Contenedores | Refleja el estado real verificado en Bloque 1 |
| Modelo de datos / ER | **Implementado y verificado** contra el esquema real de PostgreSQL (Bloque 2) |
| Máquina de estados | **Implementada y verificada** (Bloque 3): transición inválida devuelve 409 indicando los estados alcanzables |
| Secuencia de concurrencia | **Implementada y verificada empíricamente** (Bloque 2): 20 hilos simultáneos → 1 creación, 19 conflictos, 0 excepciones. Se convierte en test automatizado en Bloque 4 |
| Secuencia del consumidor | **Implementada y verificada**: 16 tests con `httpx.MockTransport` + ejecución real en `docker compose up` (10 éxitos, 1 conflicto 409, 0 fallos transitorios) |

Ver `docs/adr/` para la justificación detallada de cada decisión referenciada
aquí, y `docs/DECISIONES.md` para la bitácora narrativa del proceso completo.
