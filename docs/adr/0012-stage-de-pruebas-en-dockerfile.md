# ADR-0012: Stage `test` independiente en el Dockerfile, excluido de producción

- **Estado:** Aceptado
- **Fecha:** 2026-08-01
- **Bloque:** 4

> **En pocas palabras:** `pytest` y sus dependencias viven en un stage separado del Dockerfile y nunca llegan a la imagen de producción. El evaluador ejecuta las pruebas con un único comando adicional (`docker compose run --rm backend-tests`) sin interferir con `docker compose up`.

## Contexto

Ejecutar las pruebas dentro de un contenedor (ADR-0011) requiere que `pytest`, `pytest-cov` e `httpx` estén instalados, y que el directorio `tests/` esté presente. El Dockerfile de producción (ADR-0006) fue diseñado deliberadamente para no cargar herramientas innecesarias en la imagen que se despliega. Añadir las dependencias de prueba directamente a `requirements.txt` contradiría esa decisión.

## Decisión

Se agregan dos stages adicionales al Dockerfile existente:

- `test-deps`: parte del stage `builder` ya existente y añade las dependencias de `requirements-dev.txt` (que a su vez incluye `requirements.txt`) sin necesidad de reinstalar las dependencias base.
- `test`: imagen final de pruebas, construida como `runtime` pero copiando el directorio completo del proyecto (incluido `tests/`) y con `pytest` como `CMD`.

El stage `runtime` (producción) pasa a copiar explícitamente solo lo que la aplicación necesita en ejecución (`app/`, `alembic.ini`, `migrations/`, `entrypoint.sh`). El directorio `tests/` queda excluido de producción no por `.dockerignore` sino por la copia selectiva del stage.

En `docker-compose.yml`, el servicio `backend-tests` se declara con `profiles: ["test"]`, de modo que **no** se levanta con `docker compose up` y solo se ejecuta explícitamente con `docker compose run --rm backend-tests`.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Instalar `pytest` en `requirements.txt`, una sola imagen para todo | Contradice ADR-0006: la imagen que se despliega cargaría herramientas de prueba en producción, aumentando la superficie de ataque y el peso de la imagen sin ningún beneficio en ese contexto. |
| Un `Dockerfile.test` completamente separado | Duplicaría las instrucciones de instalación de dependencias base en dos archivos que tendrían que mantenerse sincronizados. Un único Dockerfile con múltiples stages, todos derivando del mismo `builder`, evita esa duplicación — el costo de compilación del `builder` se paga una sola vez y ambos stages lo reutilizan desde el caché. |
| El servicio `backend-tests` en Compose sin `profiles` | Correría automáticamente al levantar la solución con `docker compose up` y se vería como un contenedor que termina de inmediato (porque `pytest` no es un proceso de larga duración), lo que confundiría a cualquiera que espere levantar únicamente backend + BD + consumidor. |
| Instalar dependencias de prueba en tiempo de ejecución (`docker compose exec backend pip install pytest`) | Depende de que el contenedor tenga acceso a Internet en el momento de correr las pruebas, repite la instalación en cada ejecución y requiere permisos de escritura sobre directorios que ya tienen `chown` asignado a `appuser` desde el build. |

## Consecuencias

**Lo que se gana:**
- La imagen de producción no crece ni un byte por las pruebas: se mantiene la garantía de ADR-0006.
- El stage `test` reutiliza exactamente las mismas capas cacheadas del `builder` que ya se construyeron para producción — no hay una segunda instalación completa de `build-essential` ni de las dependencias base.
- Un evaluador ejecuta las pruebas con un único comando adicional y explícito, sin interferir con la solución en ejecución.

**Lo que se paga:**
- Un Dockerfile más largo, con cuatro stages en lugar de dos. Se documenta aquí precisamente para que ese costo de complejidad esté justificado y no parezca sobreingeniería.
