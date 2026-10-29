FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl for the HEALTHCHECK below, and nothing else. There is no compiler or
# libpq-dev: every requirement installs from a wheel, and psycopg[binary]
# bundles its own libpq. Carrying build-essential into the runtime image
# roughly doubled it (901 MB -> 470 MB without) for nothing it ever ran.
# If a future requirement does need building, add a builder stage rather
# than putting the toolchain back here.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching)
COPY requirements.txt constraints.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

RUN groupadd --gid 1000 pulse && \
    useradd --uid 1000 --gid pulse --shell /bin/bash pulse

COPY . .

RUN chown -R pulse:pulse /app

USER pulse

EXPOSE 8000

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "20"]
