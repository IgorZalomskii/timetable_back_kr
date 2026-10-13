FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
ARG APP_BASE_PATH=/
RUN npm run build -- --base "$APP_BASE_PATH"

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FORWARDED_ALLOW_IPS=127.0.0.1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home schedule
COPY --chown=schedule:schedule app ./app
COPY --chown=schedule:schedule migrations ./migrations
COPY --chown=schedule:schedule alembic.ini ./
COPY --from=frontend --chown=schedule:schedule /build/frontend/dist ./frontend/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--no-access-log"]
