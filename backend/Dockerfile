FROM python:3.12-slim AS base

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG UV_INDEX_URL=https://pypi.org/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN PIP_INDEX_URL=${PIP_INDEX_URL} pip install uv==0.5.4

COPY pyproject.toml ./
RUN UV_INDEX_URL=${UV_INDEX_URL} uv pip install --system --no-cache -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
