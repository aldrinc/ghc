# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium

EXPOSE 8008

# Override the command to run the Temporal worker:
# CMD ["python", "-m", "app.temporal.worker"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8008"]
