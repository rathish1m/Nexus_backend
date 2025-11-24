# Python 3.11 with Debian (bookworm). Stable, small, good for 1GB / 1 vCPU.
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System libs for Django GIS: GDAL, GEOS, PROJ (+ build tools)
# Note: keep 'GDAL' OFF your requirements.txt (we use system libgdal).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev \
    libgeos-dev \
    proj-bin libproj-dev \
    build-essential gcc \
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Help Django find the shared libs explicitly
ENV GDAL_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgdal.so \
    GEOS_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu/libgeos_c.so

# App dir
WORKDIR /app

# Python deps
COPY requirements.txt /app/
RUN pip install -r requirements.txt

# Project source
COPY . /app

# (Optional) collect static
# RUN python manage.py collectstatic --noinput

# Web listens on $PORT (DigitalOcean sets PORT). Use 8080 default.
EXPOSE 8080

# Healthcheck for web role only (won't break worker/beat)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD sh -c '[ "${PROCESS_TYPE:-web}" = "web" ] && python - <<PY \
import os, socket, sys; s=socket.socket(); \
s.settimeout(3); \
s.connect(("127.0.0.1", int(os.environ.get("PORT", "8080")))); \
s.close(); \
PY \
  || exit 0'

# Single CMD, switch on PROCESS_TYPE: web | worker | beat
CMD ["sh", "-c", "\
  case \"${PROCESS_TYPE:-web}\" in \
    web) \
      echo 'Starting Gunicorn (web)…'; \
      exec gunicorn nexus_backend.wsgi:application \
        --bind 0.0.0.0:${PORT:-8080} \
        --workers ${WEB_CONCURRENCY:-2} \
        --threads ${GUNICORN_THREADS:-4} \
        --timeout ${WEB_TIMEOUT:-120} \
    ;; \
    worker) \
      echo 'Starting Celery worker…'; \
      exec celery -A nexus_backend worker -l info \
        --pool=prefork --concurrency=${CELERY_CONCURRENCY:-2} -Ofair \
        -Q ${CELERY_QUEUES:-celery,default,periodic} \
        --max-tasks-per-child=${CELERY_MAX_TASKS_PER_CHILD:-200} \
    ;; \
    beat) \
      echo 'Starting Celery beat…'; \
      exec celery -A nexus_backend beat -l info \
        --scheduler ${CELERY_SCHEDULER:-django_celery_beat.schedulers:DatabaseScheduler} \
    ;; \
    *) \
      echo \"Unknown PROCESS_TYPE: ${PROCESS_TYPE}\" >&2; exit 1 \
    ;; \
  esac"]
