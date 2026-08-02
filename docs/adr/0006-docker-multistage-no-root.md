# ADR-0006: Imagen Docker multi-stage con usuario no-root

- **Estado:** Aceptado
- **Fecha:** 2026-07-31
- **Bloque:** 1 — implementado y verificado

> **En pocas palabras:** la imagen que se despliega no contiene las herramientas de compilación que se usaron para instalar las dependencias, y el proceso no corre como `root`. Dos decisiones de seguridad que van de la mano: menos herramientas disponibles para un atacante, menos privilegios si de todas formas llegara a ejecutar código.

## Contexto

El enunciado exige Dockerfiles para backend y consumidor, y en la sección de AWS exige explícitamente "principio de mínimo privilegio" por servicio. Un Dockerfile de un solo stage que instala herramientas de compilación (`build-essential`) para resolver dependencias Python con extensiones nativas (como `psycopg`) arrastra esas herramientas hasta la imagen final, aunque solo se necesiten durante la instalación. Además, por defecto los contenedores ejecutan como `root` si no se indica lo contrario.

## Decisión

**Build multi-stage:**
- Stage `builder`: tiene `build-essential` instalado. Instala todas las dependencias Python con `pip install --user`.
- Stage `runtime`: copia únicamente el directorio de paquetes ya instalados desde `builder`. Las herramientas de compilación no llegan a esta imagen.

**Usuario no-root:** se crea un usuario de sistema (`appuser`) y el proceso final (`CMD`) se ejecuta con `USER appuser`, no como `root`.

**Imagen base pinneada:** `python:3.12-slim` — versión y variante explícitas, no `latest` — para garantizar que el mismo Dockerfile produzca la misma imagen hoy y en seis meses.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Single-stage con `build-essential` en la imagen final | Imagen más pesada y con mayor superficie de ataque: un compilador C disponible dentro del contenedor en producción no aporta nada en runtime y sí facilita la vida de un atacante que ya obtuvo ejecución de código. |
| Ejecutar como `root` (comportamiento por defecto) | Viola el principio de mínimo privilegio que el propio enunciado exige para el diseño de AWS. No tendría sentido aplicarlo en la nube y omitirlo en el contenedor que se ejecuta a diario en desarrollo. |
| Imagen base `python:3.12-alpine` | Alpine usa `musl` en lugar de `glibc`. Los wheels binarios precompilados de paquetes como `psycopg[binary]` o `pydantic-core` están compilados contra `glibc` y frecuentemente no funcionan en Alpine, forzando compilación desde código fuente, con tiempos de build mucho mayores y mayor riesgo de fallos por plataforma. `slim` (basado en Debian) evita ese problema sin cargar con el peso de la imagen completa de Debian. |
| `python:latest` o sin tag de versión | Etiqueta móvil: el mismo Dockerfile podría producir una imagen diferente en el futuro sin que el Dockerfile haya cambiado, rompiendo la reproducibilidad de los builds. |

## Consecuencias

**Lo que se gana:**
- Verificable en segundos: `docker compose exec backend whoami` devuelve `appuser` (uid 999), no `root`.
- Menor superficie de ataque e imagen más liviana en el artefacto que realmente se despliega.
- El costo de compilación se paga una sola vez en el stage `builder` y queda cacheado por Docker mientras `requirements.txt` no cambie — no se repite en cada rebuild.
- El patrón es exactamente el que se recomienda para las imágenes que se subirían a ECR en la propuesta de AWS (ver `docs/aws/PROPUESTA-AWS.md`).

**Lo que se paga:**
- Un Dockerfile más largo, con más stages. Se acepta porque cada stage tiene una responsabilidad clara y está documentado, y porque es el patrón de referencia para el entorno de producción que el mismo proyecto propone.
