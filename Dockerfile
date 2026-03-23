FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    PYTHON_BIN=python

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY .env.example ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

RUN pip install --upgrade pip \
    && pip install .

RUN chmod +x ./scripts/*.sh \
    && mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/runs || exit 1

CMD ["./scripts/container_start.sh"]
