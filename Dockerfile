FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS backend-build
WORKDIR /app
COPY backend/requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home app \
    && mkdir /data \
    && chown app:app /data
WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    DATABASE_URL=sqlite:////data/groundednews.db
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
COPY --from=backend-build /opt/venv /opt/venv
COPY --chown=app:app backend/ /app/backend/
COPY --from=frontend-build --chown=app:app /app/frontend/.next/standalone /app/frontend/
COPY --from=frontend-build --chown=app:app /app/frontend/.next/static /app/frontend/.next/static/
COPY --from=frontend-build --chown=app:app /app/frontend/public /app/frontend/public/
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
USER app
VOLUME ["/data"]
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/api/stats', timeout=4)"
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/bin/bash", "/app/docker-entrypoint.sh"]
