FROM node:22.23.3-bookworm-slim AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REPOREADY_DATABASE_PATH=/data/repoready.sqlite3

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ca-certificates git nginx \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir --requirement requirements.lock

COPY backend/app ./app
COPY frontend/dist /usr/share/nginx/html
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/start.sh /usr/local/bin/repoready-start
RUN chmod +x /usr/local/bin/repoready-start && mkdir -p /data

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"

CMD ["/usr/local/bin/repoready-start"]
