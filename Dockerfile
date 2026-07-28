FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (sqlite3 useful for debugging; build-essential kept)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create persistent data directory
RUN mkdir -p /data && chown -R 1000:1000 /data

# Copy only requirements first for caching
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY . /app

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Default absolute DB path in container; can be overridden via env on Render
ENV DATABASE_URL=sqlite:////data/network_mgmt.db

# Allow external services (Render) to mount /data as persistent disk
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
