# =============================================================================
# Dockerfile del backend — build multi-stage con 4 etapas.
#
#   builder    -> instala dependencias de producción (incluye compilador).
#   runtime    -> imagen que se despliega: SOLO app/, migraciones y el
#                 entrypoint. Sin pytest, sin tests/, sin compilador.
#   test-deps  -> parte de "builder" y añade dependencias de desarrollo
#                 (pytest, httpx) sobre las mismas dependencias base.
#   test       -> imagen de pruebas: todo el proyecto (incluido tests/),
#                 usada SOLO por el servicio "tests" de docker-compose.yml
#                 (perfil "test", nunca por "docker compose up").
#
# Ver ADR-0006 (multi-stage + no-root) y ADR-0012 (por qué el stage de
# pruebas está separado del de producción).
# =============================================================================

# ---- Stage 1: builder --------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Stage 2: runtime (imagen de producción) -----------------------------
FROM python:3.12-slim AS runtime

# Usuario no-root: principio de mínimo privilegio también a nivel de
# contenedor local (mismo criterio que se exige después para AWS).
RUN groupadd --system appuser && useradd --system --gid appuser appuser

WORKDIR /app

# Copiar únicamente los paquetes ya instalados por pip --user (sin compilador).
COPY --from=builder /root/.local /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copia SELECTIVA (no "COPY . ."): la imagen que se despliega lleva solo lo
# que la aplicación necesita en ejecución. tests/, pytest.ini, requirements-
# dev.txt, etc. no entran a esta imagen aunque existan en el contexto de build.
COPY app/ ./app/
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY entrypoint.sh ./

RUN mkdir -p /app/logs \
    && chmod +x /app/entrypoint.sh \
    && chown -R appuser:appuser /app /home/appuser/.local

USER appuser

EXPOSE 8000

# El entrypoint aplica las migraciones de Alembic antes de arrancar Uvicorn,
# de modo que la API nunca atiende peticiones contra un esquema desactualizado.
CMD ["/app/entrypoint.sh"]

# ---- Stage 3: test-deps (dependencias de desarrollo) ---------------------
# Parte de "builder" (que ya tiene las dependencias base instaladas) y añade
# encima pytest/httpx/pytest-cov. Evita reinstalar desde cero las
# dependencias de producción para las pruebas.
FROM builder AS test-deps

COPY requirements-dev.txt .
RUN pip install --no-cache-dir --user -r requirements-dev.txt

# ---- Stage 4: test (imagen de pruebas, NUNCA se despliega) ---------------
FROM python:3.12-slim AS test

RUN groupadd --system appuser && useradd --system --gid appuser appuser

WORKDIR /app

COPY --from=test-deps /root/.local /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Aquí sí se copia todo el proyecto: tests/, pytest.ini, alembic.ini, etc.
COPY . .

RUN mkdir -p /app/logs /app/htmlcov \
    && chmod +x /app/entrypoint.sh \
    && chown -R appuser:appuser /app /home/appuser/.local

USER appuser

CMD ["pytest"]
