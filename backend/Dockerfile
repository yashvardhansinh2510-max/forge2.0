# Forge/BuildCon House backend — reproducible production image.
# Build:  docker build -t buildcon-backend ./backend
# Run:    docker run -p 8000:8000 --env-file <secrets> buildcon-backend
# All configuration comes from the process environment (see settings.py);
# never bake .env into the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install -r requirements-prod.txt

COPY . .

RUN useradd --create-home forge && chown -R forge:forge /app
USER forge

EXPOSE 8000

# /api/health returns 503 when Mongo is unreachable, so this doubles as a
# readiness signal for the orchestrator.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
