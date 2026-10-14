FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY sme_copilot ./sme_copilot
COPY config ./config
COPY frontend ./frontend
COPY seed ./seed
COPY pyproject.toml README.md ./

# Run as an unprivileged user; data (SQLite, reports, logs) lives in a volume.
RUN useradd --create-home --uid 10001 copilot && mkdir -p /app/data && chown -R copilot /app/data
USER copilot

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health').status==200 else 1)"

# Default: serve with existing data. docker-compose overrides this with the one-command demo.
CMD ["python", "-m", "sme_copilot.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
