# =============================================================================
# Dockerfile del consumidor — mismo patrón multi-stage que backend/Dockerfile
# (ver ADR-0006 y ADR-0012), adaptado a que este servicio no necesita
# compilar nada: httpx, pydantic-settings y structlog tienen wheels
# precompilados para esta plataforma, así que el stage "builder" no instala
# build-essential (a diferencia del backend, que sí lo necesita por psycopg).
# =============================================================================

# ---- Stage 1: builder --------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Stage 2: runtime (imagen que se ejecuta) ----------------------------
FROM python:3.12-slim AS runtime

RUN groupadd --system appuser && useradd --system --gid appuser appuser

WORKDIR /app

COPY --from=builder /root/.local /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copia selectiva: solo el paquete de la aplicación, no tests/ ni archivos de
# desarrollo (mismo criterio que backend/Dockerfile).
COPY app/ ./app/

RUN mkdir -p /app/logs \
    && chown -R appuser:appuser /app /home/appuser/.local

USER appuser

# Proceso de un solo lote (ver ADR-0014): se ejecuta, produce su resultado y
# termina. No expone ningún puerto: nadie más se conecta a este contenedor.
CMD ["python", "-m", "app.main"]

# ---- Stage 3: test-deps ---------------------------------------------------
FROM builder AS test-deps

COPY requirements-dev.txt .
RUN pip install --no-cache-dir --user -r requirements-dev.txt

# ---- Stage 4: test ---------------------------------------------------------
FROM python:3.12-slim AS test

RUN groupadd --system appuser && useradd --system --gid appuser appuser

WORKDIR /app

COPY --from=test-deps /root/.local /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY . .

RUN mkdir -p /app/logs \
    && chown -R appuser:appuser /app /home/appuser/.local

USER appuser

CMD ["pytest"]
