# ADR-0016: Duplicación deliberada de catálogos entre backend y consumidor

- **Estado:** Aceptado
- **Fecha:** 2026-08-02
- **Bloque:** Auditoría post-entrega (decisión tomada originalmente al construir el consumidor, formalizada aquí)

## Contexto

`consumer/app/generador_datos.py` repite, como constantes de texto plano
(`_TIPOS`, `_PRIORIDADES`), los mismos valores de catálogo que
`backend/app/domain/enums.py` define como fuente única de verdad para el
backend. El código citaba esta decisión como ya justificada "en el ADR de
este bloque" — una referencia que nunca se formalizó como ADR. Este documento
la cierra.

## Decisión

El consumidor **no** importa ni depende del paquete de dominio del backend
(`app/domain/enums.py`). Los valores de catálogo que necesita para construir
solicitudes de prueba se declaran de forma independiente, como constantes
propias.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Extraer un paquete Python compartido (`shared/` o una librería interna) con los catálogos, importado por ambos servicios | Introduce acoplamiento en tiempo de **compilación/importación** entre dos servicios que el propio enunciado describe como "independientes". Un cambio de catálogo en el backend rompería el consumidor al desplegarlo (`ImportError` o un valor inesperado), en vez de manifestarse como lo haría con cualquier integrador externo real: un `422` HTTP la primera vez que el valor ya no es válido. Un sistema externo real —que es lo que el consumidor simula— jamás tendría acceso al código Python interno del backend, solo a su contrato HTTP documentado (OpenAPI). |
| Publicar los catálogos en un archivo de configuración compartido (YAML/JSON) montado en ambos contenedores | Sigue acoplando el ciclo de despliegue de ambos servicios a un artefacto compartido y añade una pieza de infraestructura (el archivo, su montaje, su versionado) para un problema que el contrato HTTP ya resuelve sin esfuerzo adicional. |
| Que el consumidor consulte los catálogos válidos en tiempo de ejecución (p. ej. un endpoint `GET /catalogos`) | El enunciado no define ni pide ese endpoint; añadirlo solo para uso interno del consumidor sería alcance no solicitado, y seguiría sin ser necesario: el consumidor no necesita la lista completa de valores válidos, solo necesita generar *algunos* valores válidos para su lote de demostración. |

## Consecuencias

**A favor:**
- Los dos servicios se pueden versionar, desplegar y modificar de forma
  independiente, que es la propiedad que el enunciado pide explícitamente al
  llamarlos "servicios backend independientes".
- Si el backend agrega o quita un valor de catálogo sin coordinar con el
  consumidor, el síntoma es un `422` en el log del consumidor (visible,
  accionable, exactamente el comportamiento que tendría cualquier integrador
  externo real) y no un fallo de importación o un `KeyError` en un punto
  distinto del código.
- El costo de sincronización manual es bajo: son 4 y 3 valores
  respectivamente, que cambian con muy poca frecuencia.

**Costo asumido — y un matiz importante:**
Este mismo argumento **no se extiende automáticamente a cualquier código
duplicado entre los dos servicios**. La configuración de logging
(`backend/app/core/logging.py` vs. `consumer/app/core/logging_setup.py`) está
duplicada con una justificación distinta y más débil: no es "dominio de
negocio con contrato HTTP de por medio", es infraestructura interna sin
ningún contrato que la desacople. Ahí el argumento de este ADR no aplica
igual de bien, y el costo real es que una constante como el tamaño de
rotación de logs (`10 * 1024 * 1024`) puede divergir entre ambos archivos sin
que nada lo detecte. Se documenta esta distinción explícitamente para no
generalizar "duplicar entre servicios siempre está bien" a partir de un caso
(catálogos) donde sí lo está.
