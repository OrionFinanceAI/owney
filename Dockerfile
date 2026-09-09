# syntax=docker/dockerfile:1
# Build:
#   docker build -t owney:latest .
#
# Run (env vars supplied by ECS task definition or local -e flags):
#   docker run --rm --env-file .env owney:latest owney:usdc
#   docker run --rm --env-file .env owney:latest owney:weth

FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends tini && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY docker-entrypoint.sh ./

RUN pip install --no-cache-dir . && \
    chmod +x docker-entrypoint.sh && \
    addgroup --system keeper && adduser --system --ingroup keeper keeper && \
    chown -R keeper:keeper /app

USER keeper

ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]
CMD ["owney:usdc"]
