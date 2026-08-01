# Servicio de Gestión de Solicitudes Institucionales

> **Estado del proyecto:** en construcción (prueba técnica Backend Developer
> Semi Senior). Este README se completa íntegramente en el bloque final del
> desarrollo con arquitectura, endpoints, variables de entorno, decisiones,
> limitaciones y matriz de cumplimiento. Mientras tanto, la documentación
> formal del proyecto vive en:

- [`docs/adr/`](docs/adr/README.md) — Architecture Decision Records (decisiones de arquitectura, formato estándar).
- [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md) — diagramas C4, modelo de datos y secuencias (Mermaid).
- [`docs/aws/PROPUESTA-AWS.md`](docs/aws/PROPUESTA-AWS.md) — propuesta de despliegue e integración en AWS.

## Licencia

Este proyecto se distribuye bajo licencia [MIT](LICENSE): cualquiera puede
usar, copiar o modificar el código (incluso comercialmente), siempre que se
mantenga el aviso de copyright original. La licencia **no transfiere
autoría** — el copyright y la titularidad del proyecto son de Ricardo MB.

## Ejecutar (estado actual del proyecto)

```bash
cp .env.example .env
docker compose up --build
curl http://localhost:8000/health
```

En este punto del desarrollo (Bloque 1 de 6), el sistema levanta PostgreSQL y
el backend con un endpoint de verificación de vida (`/health`). El resto de
funcionalidad (endpoints de negocio, migraciones, consumidor, pruebas) se
agrega de forma incremental — ver la bitácora para el detalle de cada bloque.
