# ADR-0012: Stage `test` independiente en el Dockerfile, excluido de producción

- **Estado:** Aceptado
- **Fecha:** 2026-08-01
- **Bloque:** 4

## Contexto

Ejecutar las pruebas dentro de un contenedor (ADR-0011) requiere que `pytest`,
`pytest-cov` y `httpx` estén instalados, y que el directorio `tests/` esté
presente en la imagen. El Dockerfile de producción (ADR-0006) fue diseñado
deliberadamente para **no** cargar herramientas innecesarias en la imagen que
se despliega. Añadir las dependencias de prueba directamente a
`requirements.txt` contradiría esa decisión ya tomada.

## Decisión

Se agrega un tercer y cuarto stage al Dockerfile existente:

- `test-deps`: parte del stage `builder` ya existente y añade las dependencias
  de `requirements-dev.txt` (que a su vez incluye `requirements.txt`) sobre la
  misma base.
- `test`: imagen final de pruebas, construida igual que `runtime` pero
  copiando el directorio completo del proyecto (incluido `tests/`) y con
  `pytest` como `CMD`.

El stage `runtime` (producción) deja de hacer `COPY . .` y pasa a copiar
explícitamente solo lo que la aplicación necesita en ejecución
(`app/`, `alembic.ini`, `migrations/`, `entrypoint.sh`). El directorio
`tests/` deja de estar excluido en `.dockerignore` —ya que ahora sí hace falta
en el stage de pruebas— y en su lugar la exclusión se logra por la copia
selectiva del stage `runtime`.

En `docker-compose.yml`, el servicio `tests` se declara con
`profiles: ["test"]`, de modo que **no** se levanta con `docker compose up`
(que debe iniciar únicamente "la solución", tal como exige el enunciado) y solo
se ejecuta explícitamente con `docker compose run --rm tests`.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Instalar `pytest` y compañía en `requirements.txt` (una sola imagen para todo) | Contradice ADR-0006: la imagen que se despliega cargaría herramientas de prueba en producción, aumentando superficie de ataque y tamaño sin ningún beneficio en ese contexto. |
| Un `Dockerfile.test` completamente separado | Duplicaría las instrucciones de instalación de dependencias base (`builder`) en dos archivos que tendrían que mantenerse sincronizados. Un único Dockerfile con múltiples *stages*, todos derivando del mismo `builder`, evita esa duplicación. |
| Ejecutar `docker compose up` con el servicio `tests` sin `profiles` | Correría automáticamente al levantar la solución, mostrándose como un contenedor que se detiene inmediatamente después de correr una vez (`pytest` no es un proceso de larga duración), lo cual es confuso frente al requisito de que `docker compose up --build` levante "la solución" (backend + BD + consumidor), no la suite de pruebas. |
| Instalar las dependencias de prueba en tiempo de ejecución (`docker compose exec backend pip install pytest && pytest`) | Depende de que el contenedor tenga acceso a Internet en el momento de correr las pruebas y repite la instalación en cada ejecución en lugar de quedar fijada en la imagen; además exigiría permisos de escritura en un directorio que pertenece a `appuser` con `chown` ya aplicado en el build. |

## Consecuencias

**A favor:**
- La imagen de producción no crece ni un byte por causa de las pruebas: se
  mantiene la garantía de ADR-0006.
- Un evaluador ejecuta las pruebas con un único comando adicional y explícito
  (`docker compose run --rm tests`), sin interferir con
  `docker compose up --build`.
- El stage `test` reutiliza exactamente las mismas capas cacheadas del
  `builder` que ya se construyeron para producción — no hay una segunda
  instalación completa de `build-essential` ni de las dependencias base.

**Costo asumido:**
- Un Dockerfile más largo, con cuatro *stages* en lugar de dos. Se documenta
  aquí precisamente para que ese costo de complejidad esté justificado y no
  sea "porque sí".
