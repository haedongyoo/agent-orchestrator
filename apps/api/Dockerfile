# ── API / Orchestrator Image ───────────────────────────────────────────────────
FROM python:3.12-slim AS base

# gcc is needed to compile asyncpg's C extension on platforms without a wheel
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install deps in a separate layer so they're cached between code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

EXPOSE 8000

# Default: run the API server.
# Overridden per-service in docker-compose (worker / beat / migrate).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
