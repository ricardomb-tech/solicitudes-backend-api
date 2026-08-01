# ADR-0006: Imagen Docker multi-stage con usuario no-root

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 1 — implementado y verificado

## Contexto

El enunciado exige Dockerfiles para backend y consumidor, y en la sección de
AWS exige explícitamente "principio de mínimo privilegio" por servicio. Un
Dockerfile de un solo *stage* que instala herramientas de compilación
(`build-essential`) para resolver dependencias Python con extensiones nativas
(p. ej. `psycopg`) arrastra esas herramientas hasta la imagen final, aunque
solo se necesiten durante la instalación. Además, por defecto los contenedores
ejecutan como `root` si no se indica lo contrario.

## Decisión

- **Build multi-stage:** un stage `builder` (con `build-essential`) instala
  las dependencias de Python con `pip install --user`; un stage `runtime`
  copia únicamente el directorio de paquetes ya instalados
  (`/root/.local` → `/home/appuser/.local`), sin las herramientas de
  compilación.
- **Usuario no-root:** se crea un usuario de sistema (`appuser`) y el proceso
  final (`CMD`) se ejecuta con `USER appuser`, no como `root`.
- **Imagen base pinneada:** `python:3.12-slim` (versión y variante explícitas,
  no `latest` ni la versión más reciente del lenguaje) para builds
  reproducibles.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Single-stage con `build-essential` en la imagen final | Imagen más pesada y con mayor superficie de ataque (un compilador C disponible dentro del contenedor en producción no aporta nada en runtime y sí ayuda a un atacante que ya obtuvo ejecución de código). |
| Ejecutar como `root` (comportamiento por defecto, no requiere cambios) | Viola el principio de mínimo privilegio exigido explícitamente para el diseño de AWS; se aplica el mismo criterio ya desde el entorno local por consistencia — no tendría sentido exigirlo en la nube y omitirlo en el contenedor que se ejecuta a diario en desarrollo. |
| Imagen base `python:3.12-alpine` | Alpine usa `musl` en lugar de `glibc`, lo que frecuentemente rompe la resolución de *wheels* binarios precompilados de paquetes como `psycopg[binary]` o `pydantic-core` (compilados contra `glibc`), forzando compilación desde código fuente y aumentando tiempo de build y riesgo de fallos por plataforma. `slim` (basado en Debian) evita ese problema sin cargar con el tamaño de la imagen completa de Debian. |
| `python:latest` o sin tag de versión | Etiqueta móvil: el mismo Dockerfile podría producir una imagen distinta en el futuro sin que el Dockerfile haya cambiado, rompiendo reproducibilidad de builds. |

## Consecuencias

**A favor:**
- Verificado empíricamente: `docker compose exec backend whoami` devuelve
  `appuser` (uid 999), no `root` — reproducible por cualquiera con la
  solución en ejecución.
- Menor superficie de ataque e imagen más liviana en el artefacto que
  realmente se despliega.
- El costo de compilación (instalar `build-essential`, ~170s la primera vez)
  se paga una sola vez en el *stage* `builder` y queda cacheado por Docker
  mientras `requirements.txt` no cambie; no se repite en cada rebuild.

**Costo asumido:**
- Dockerfile más largo y con más partes móviles que una versión single-stage.
  Se acepta porque es exactamente el patrón que se recomienda replicar para
  las imágenes que se subirían a ECR en la propuesta de AWS (ver
  `docs/aws/PROPUESTA-AWS.md`).
