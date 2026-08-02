# ADR-0016: Duplicación deliberada de catálogos entre backend y consumidor

- **Estado:** Aceptado
- **Fecha:** 2026-08-02
- **Bloque:** Auditoría post-entrega (decisión tomada al construir el consumidor, formalizada aquí)

> **En pocas palabras:** el consumidor no importa el código Python del backend para conocer los valores de catálogo válidos. Los declara como sus propias constantes. Un sistema externo real jamás tendría acceso al código interno de otro servicio — solo a su contrato HTTP. El consumidor simula exactamente eso.

## Contexto

`consumer/app/generador_datos.py` repite, como constantes de texto, los mismos valores de catálogo (`_TIPOS`, `_PRIORIDADES`) que `backend/app/domain/enums.py` define como fuente única de verdad para el backend. Una auditoría señaló que esta duplicación no estaba documentada como decisión consciente. Este ADR la cierra.

## Decisión

El consumidor **no** importa ni depende del paquete de dominio del backend (`app/domain/enums.py`). Los valores de catálogo que necesita para construir solicitudes de prueba se declaran como constantes propias e independientes.

## Alternativas consideradas

| Alternativa | Por qué se descartó |
|---|---|
| Extraer un paquete Python compartido (`shared/`) importado por ambos servicios | Introduce acoplamiento en tiempo de compilación entre dos servicios que el enunciado describe como "independientes". Un cambio de catálogo en el backend rompería el consumidor al desplegarlo (`ImportError` o un valor inesperado) en lugar de manifestarse como lo haría con cualquier integrador externo real: un `422` HTTP la primera vez que el valor ya no es válido. Un sistema externo real jamás tendría acceso al código Python interno del backend. |
| Publicar los catálogos en un archivo de configuración compartido (YAML/JSON) montado en ambos contenedores | Sigue acoplando el ciclo de despliegue de ambos servicios a un artefacto compartido y añade infraestructura adicional (el archivo, su montaje, su versionado) para un problema que el contrato HTTP ya resuelve sin esfuerzo. |
| Que el consumidor consulte los catálogos válidos en tiempo de ejecución (un endpoint `GET /catalogos`) | El enunciado no define ese endpoint. Añadirlo solo para uso interno del consumidor es alcance no solicitado. Además, el consumidor no necesita la lista completa de valores — solo necesita generar algunos valores válidos para su lote de demostración. |

## Consecuencias

**Lo que se gana:**
- Los dos servicios se pueden versionar, desplegar y modificar de forma independiente — la propiedad que el enunciado pide al llamarlos "servicios backend independientes".
- Si el backend agrega o quita un valor de catálogo sin coordinar con el consumidor, el síntoma es un `422` visible en los logs del consumidor (exactamente el comportamiento de cualquier integrador externo real), no un fallo de importación en un punto distinto del código.
- El costo de sincronización manual es bajo: son 4 y 3 valores respectivamente, que cambian con poca frecuencia.

**Lo que se paga — y un matiz importante:**
Este argumento **no se extiende automáticamente a cualquier código duplicado entre los dos servicios**. La configuración de logging (`backend/app/core/logging.py` vs. `consumer/app/core/logging_setup.py`) está duplicada con una justificación mucho más débil: no es "dominio de negocio con contrato HTTP de por medio", es infraestructura interna sin ningún contrato que la desacople. Ahí el argumento de este ADR no aplica igual de bien — una constante como el tamaño de rotación de logs puede divergir entre ambos archivos sin que nada lo detecte. Se documenta esta distinción explícitamente para no generalizar "duplicar entre servicios siempre está bien" a partir de un caso donde sí lo está.
