FROM python:3.11-slim

# --- System deps (GDAL/GEOS/PROJ + build tools) ---
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev libgeos-dev proj-bin libproj-dev postgresql-client\
    build-essential gcc \
    # optional but useful:
    curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Python setup
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Leverage Docker layer caching for deps
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# make sure the logs directory exists
RUN mkdir -p /app/core/logs

# Copy and make the startup script executable
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Default envs (override in Render/compose as needed)
ENV DJANGO_SETTINGS_MODULE=core.settings \
    WEB_CONCURRENCY=2

# Expose app port (for local compose)
EXPOSE 8000

# Use the startup script instead of direct gunicorn
CMD ["/app/start.sh"]