# ADR-0015: Valores por defecto en `docker-compose.yml` y publicación solo en localhost

- **Estado:** Aceptado
- **Fecha:** 2026-08-02
- **Bloque:** Auditoría post-entrega

## Contexto

El enunciado exige, en dos frases distintas, cosas que en la implementación original de `docker-compose.yml` entraban en tensión:

1. *"La solución deberá ejecutarse mediante: `docker compose up --build`"* — sin ningún paso previo mencionado en esa frase.
2. *"Credenciales fuera del código y del repositorio"*.

La implementación inicial resolvía (2) correctamente (`.env` gitignored, `env_file: - .env` obligatorio) pero rompía (1): en un clon recién descargado, sin haber ejecutado `cp .env.example .env` todavía, Compose abortaba con `env file .env not found`. Se verificó empíricamente clonando el repositorio a una carpeta limpia y ejecutando el comando tal cual aparece en el enunciado.

Adicionalmente, una auditoría de seguridad señaló que `ports: - "8000:8000"` publica el backend en **todas** las interfaces de red del host (`0.0.0.0`), no solo en `localhost` — relevante porque la API no tiene autenticación (fuera de alcance declarado) y sí devuelve datos personales (nombre, correo) en sus respuestas.

## Decisión

**1. Valores por defecto con la sintaxis `${VAR:-default}` de Compose**, idénticos a los de `.env.example`, en cada variable que los servicios `backend`, `consumer` y `backend-tests` necesitan. `env_file` pasa de ser una lista simple a la forma `- path: .env / required: false`, de modo que la ausencia del archivo ya no aborta el arranque.

Si existe un `.env` real, sus valores tienen prioridad: Compose sustituye `${VAR}` usando el entorno del shell y el `.env` de nivel de proyecto **antes** de aplicar el resultado a cada servicio — el mecanismo de sustitución de variables de Compose es independiente del `env_file:` de un servicio concreto.

**2. El puerto del backend se publica como `127.0.0.1:8000:8000`**, no `8000:8000` (equivalente a `0.0.0.0:8000:8000`).

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Mantener `env_file: - .env` obligatorio y documentar el paso `cp .env.example .env` solo en el README | Es lo que había, y falla exactamente ante la interpretación más literal posible del enunciado: pegar el comando citado textualmente. Un evaluador no está obligado a leer el README completo antes de probar el comando que el propio enunciado le dio. |
| Commitear un `.env` real al repositorio con los valores de desarrollo | Contradice directamente "credenciales fuera del código y del repositorio" — aunque sean credenciales de desarrollo no sensibles, commitear el archivo que el propio `.gitignore` existe para excluir sería una inconsistencia flagrante, no una solución. |
| Generar el `.env` automáticamente desde un script de `postCreate` o un target de `Makefile` | Añade una herramienta y un paso indirecto para resolver algo que Compose ya soporta de forma nativa con `${VAR:-default}`. Más partes móviles sin beneficio adicional. |
| Publicar el backend en `0.0.0.0` y confiar en el firewall del host | Depende de una configuración externa al proyecto que no se puede verificar ni garantizar; el propio servicio `db` ya aplicaba el criterio contrario (ni siquiera publica puerto) con una justificación explícita — dejar `backend` en `0.0.0.0` era una inconsistencia con el propio criterio de seguridad ya aplicado en el mismo archivo. |

## Consecuencias

**A favor:**
- Verificado empíricamente: `docker compose down -v && mv .env .env.bak && docker compose up --build` (sin `.env` en absoluto) levanta `db`, `backend` y `consumer` correctamente, con `db` y `backend` en estado `healthy`.
- Los valores por defecto son exactamente los mismos que ya eran públicos en `.env.example` (`changeme_dev_password` — un placeholder, no un secreto real); no se introduce ninguna credencial nueva ni se relaja la política de secretos reales, que en un despliegue real (AWS) vendrían de Secrets Manager y nunca de un valor por defecto en este archivo (ver `docs/aws/PROPUESTA-AWS.md`).
- `127.0.0.1:8000` reduce la superficie de exposición sin cambiar ningún flujo de desarrollo local (Swagger, curl, Bruno siguen funcionando exactamente igual contra `localhost:8000`).

**Costo asumido:**
- Los valores de desarrollo (usuario, contraseña placeholder, nombre de BD) ahora aparecen duplicados en dos archivos (`.env.example` y `docker-compose.yml`) en vez de uno solo. Se acepta el riesgo de deriva entre ambos porque son valores de desarrollo no sensibles y de bajo cambio; un `.env` real siempre los sobreescribe.
- Quien necesite acceder a la API desde otro equipo de su red local (no solo `localhost`) debe saberlo y cambiarlo explícitamente — es exactamente el comportamiento deseado, no una limitación accidental.
