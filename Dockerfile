# GPHA Internal Audit Workspace (GIAW) - application image.
# Built on the server by deploy/vps/install.sh (docker compose build); nothing secret is baked in:
# every setting comes from the environment (.env.production on the server).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first (cached between builds), exactly as locked in uv.lock.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY mysql ./mysql

# Run as an unprivileged user; uploads and backups live on mounted volumes.
RUN useradd --uid 10001 --no-create-home --home-dir /app --shell /usr/sbin/nologin giaw \
    && mkdir -p /data/uploads /data/backups \
    && chown -R giaw:giaw /data
USER giaw

ENV GPHA_UPLOAD_DIR=/data/uploads \
    GPHA_BACKUP_DIR=/data/backups

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/', timeout=4).status == 200 else 1)"

# init_db applies migrations and creates the first administrator, then the server starts.
# Caddy (the HTTPS front door) is the only proxy that can reach this port.
CMD ["sh", "-c", "python -m scripts.init_db && exec uvicorn app.main:app --host 0.0.0.0 --port 8001 --proxy-headers --forwarded-allow-ips '*'"]
