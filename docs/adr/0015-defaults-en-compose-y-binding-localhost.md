# ADR-0015: Valores por defecto en `docker-compose.yml` y publicación solo en localhost

- **Estado:** Aceptado
- **Fecha:** 2026-08-02
- **Bloque:** Auditoría post-entrega

> **En pocas palabras:** `docker compose up --build` funciona sin ningún paso previo, incluso si no existe el archivo `.env`. Los valores de desarrollo están embebidos como defaults en el propio Compose. Además, el backend solo escucha en `127.0.0.1`, no en todas las interfaces de red, porque la API no tiene autenticación y devuelve datos personales.

## Contexto

El enunciado exige dos cosas que en la implementación original entraban en tensión:

1. *"La solución deberá ejecutarse mediante: `docker compose up --build`"* — sin ningún paso previo mencionado.
2. *"Credenciales fuera del código y del repositorio"*.

La implementación inicial resolvía (2) correctamente (`.env` gitignored, `env_file: - .env` obligatorio) pero rompía (1): en un clon recién descargado, sin haber ejecutado `cp .env.example .env`, Compose abortaba con `env file .env not found`. Verificado empíricamente clonando el repositorio a una carpeta limpia y pegando el comando exacto del enunciado.

Adicionalmente, una auditoría de seguridad señaló que `ports: - "8000:8000"` publica el backend en **todas** las interfaces del host (`0.0.0.0`), no solo en `localhost`. La API no tiene autenticación (fuera de alcance declarado) y devuelve datos personales (nombre, correo), por lo que publicarla en todas las interfaces era un riesgo evitable.

## Decisión

**1. Valores por defecto con la sintaxis `${VAR:-default}` de Compose**, idénticos a los de `.env.example`. `env_file` pasa de ser obligatorio a `required: false`, de modo que la ausencia del archivo no aborta el arranque.

Si existe un `.env` real, sus valores tienen prioridad: Compose sustituye las variables usando el entorno del shell y el `.env` de nivel de proyecto antes de aplicar el resultado a cada servicio.

**2. El puerto del backend se publica como `127.0.0.1:8000:8000`**, no `8000:8000` (que equivale a `0.0.0.0:8000:8000`).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Mantener `env_file` obligatorio y documentar `cp .env.example .env` solo en el README | Es lo que había, y falla ante la interpretación más literal del enunciado: pegar el comando textualmente sin leer el README completo. Un evaluador no está obligado a leer toda la documentación antes de probar el comando que el enunciado le da. |
| Commitear un `.env` real al repositorio con los valores de desarrollo | Contradice directamente "credenciales fuera del código y del repositorio". Aunque sean valores de desarrollo no sensibles, commitear el archivo que el propio `.gitignore` existe para excluir es una inconsistencia que cualquier evaluador detectaría de inmediato. |
| Generar el `.env` desde un script de `Makefile` o `postCreate` | Añade herramientas y pasos indirectos para resolver algo que Compose ya soporta de forma nativa con `${VAR:-default}`. Más complejidad sin beneficio. |
| Publicar el backend en `0.0.0.0` confiando en el firewall del host | Depende de una configuración externa al proyecto que no se puede verificar. El propio servicio `db` ya no publicaba ningún puerto al host; dejar `backend` en `0.0.0.0` era inconsistente con el criterio de seguridad ya aplicado en el mismo archivo. |

## Consecuencias

**Lo que se gana:**
- Verificado empíricamente: `docker compose down -v && mv .env .env.bak && docker compose up --build` (sin `.env` en absoluto) levanta los tres servicios correctamente y los deja en estado `healthy`.
- Los valores por defecto son exactamente los mismos que ya eran públicos en `.env.example` (`changeme_dev_password` — un placeholder, no un secreto real). No se relaja la política de secretos reales, que en producción vendrían de Secrets Manager, nunca de un valor por defecto de Compose.
- `127.0.0.1:8000` reduce la superficie de exposición sin cambiar ningún flujo de desarrollo local: Swagger, curl y Bruno siguen funcionando exactamente igual contra `localhost:8000`.

**Lo que se paga:**
- Los valores de desarrollo aparecen duplicados en `.env.example` y en `docker-compose.yml`. Se acepta porque son valores de desarrollo no sensibles y de bajo cambio; un `.env` real siempre los sobreescribe.
- Quien necesite acceder a la API desde otro equipo de su red local debe saberlo y cambiar el binding explícitamente — lo cual es exactamente el comportamiento deseado.
