# Built from the repo root; the server uses avenoxbeyin's scripts/ and template/ folders:
#   docker build -f coach/Dockerfile -t coach .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    COACH_DATA_DIR=/data COACH_HOST=0.0.0.0 PORT=8000 \
    COACH_ENGINE_DIR=/opt/avenoxbeyin

# avenoxbeyin engine: each user's vault is installed with its install_v3.py.
COPY VERSION /opt/avenoxbeyin/VERSION
COPY scripts /opt/avenoxbeyin/scripts
COPY template /opt/avenoxbeyin/template

WORKDIR /app
COPY coach/pyproject.toml coach/README.md ./
COPY coach/coach ./coach
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir . && useradd --create-home --uid 10001 coach && mkdir -p /data && chown coach /data

USER coach
# Persistent disk comes from the platform (Railway Volume or docker run -v ...:/data).
# No VOLUME line: Railway rejects it.
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health')"
CMD ["coach-server"]
