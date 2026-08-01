# =============================================================================
# Dockerfile del backend — build multi-stage.
#
# Stage "builder": instala dependencias, incluyendo herramientas de
# compilación que algunos paquetes Python pueden necesitar según la
# arquitectura/plataforma donde se construya la imagen.
# Stage "runtime": copia SOLO los paquetes ya instalados, no las herramientas
# de compilación. Resultado: una imagen final más pequeña y con menor
# superficie de ataque, pagando el costo de compilación una sola vez y
# descartándolo antes de la imagen que realmente se despliega.
# =============================================================================

# ---- Stage 1: builder --------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Stage 2: runtime ----------------------------------------------------
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

COPY . .

RUN mkdir -p /app/logs \
    && chown -R appuser:appuser /app /home/appuser/.local

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
