# syntax=docker/dockerfile:1
FROM python:3.12.12-slim-bookworm AS builder
WORKDIR /app
COPY backend/requirements.lock /app/requirements.lock
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then PIP_CERT=/run/secrets/proxy_ca pip install --no-cache-dir --prefix=/install -r /app/requirements.lock; \
    else pip install --no-cache-dir --prefix=/install -r /app/requirements.lock; fi
FROM python:3.12.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend/src
WORKDIR /app/backend
COPY --from=builder /install /usr/local
COPY --chown=10001:10001 backend /app/backend
RUN groupadd -g 10001 workforce && useradd -u 10001 -g workforce -M -s /usr/sbin/nologin workforce && mkdir -p /var/lib/workforce/artifacts && chown -R workforce:workforce /var/lib/workforce
ENTRYPOINT ["python", "-m", "workforce.entrypoint"]
CMD ["uvicorn", "workforce.main:app", "--host", "0.0.0.0", "--port", "8000"]
