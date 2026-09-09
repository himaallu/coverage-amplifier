# Stage 1: Build dependencies in a clean virtual environment
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Stage 2: Minimal runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PATH="/opt/venv/bin:$PATH"

# Create dedicated non-root user
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -s /bin/bash -m appuser

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy backend application source, prompts, and database migrations
COPY backend /app/backend
COPY prompts /app/prompts
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8080

# Cloud Run dynamic PORT injection
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
