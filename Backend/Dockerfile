FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: editing app code must not reinstall 60 packages.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# alembic/ is in the image so a one-off container can run migrations from the
# laptop's `docker run --rm` even though Render itself never runs them.
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Nothing here needs root: the app writes only to /tmp and talks to Postgres and
# object storage over the network.
RUN useradd --uid 10001 --create-home app
USER app

# One process. Render's free instance is 512 MB, two uvicorn workers plus a PDF
# rasterisation would not fit, and the in-memory rate limiter is per process
# either way. Render injects PORT; the default keeps plain `docker run` working.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1"]
