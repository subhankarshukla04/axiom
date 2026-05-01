FROM python:3.12-slim

WORKDIR /app

# Install gcc for psycopg2 and other compiled deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create writable directories
RUN mkdir -p /data /tmp/logs /tmp/yfinance

# Environment defaults — override at runtime
ENV DATABASE_TYPE=sqlite \
    SQLITE_DB=/data/valuations.db \
    FLASK_ENV=production \
    LOG_LEVEL=INFO \
    PORT=8000

EXPOSE 8000

# Persistent data volume (SQLite DB)
VOLUME ["/data"]

CMD python -m gunicorn app:app \
    --bind 0.0.0.0:${PORT} \
    --workers 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
