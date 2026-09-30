# The web app in one container: the built pages and the API with the engine.
#   docker compose -f deploy/docker-compose.yml up -d --build app
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
# GL runtime for OpenCascade and pymeshlab (as in CI)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglu1-mesa libegl1 libxrender1 libxext6 libxi6 libxkbcommon0 \
      libglib2.0-0 libdbus-1-3 libfontconfig1 libsm6 libice6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY engine/ engine/
COPY apps/api/ apps/api/
COPY config/ config/
RUN uv sync --frozen --no-dev --all-packages
COPY --from=web /web/dist apps/web/dist
ENV COVER_DATA_DIR=/data COVER_HOST=0.0.0.0 COVER_PORT=8080 PATH=/app/.venv/bin:$PATH
EXPOSE 8080
CMD ["cover-web"]
