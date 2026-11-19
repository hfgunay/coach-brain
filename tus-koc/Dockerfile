# Repo kökünden derlenir; sunucu avenoxbeyin'in scripts/ ve template/ klasörlerini kullanır:
#   docker build -f tus-koc/Dockerfile -t tus-koc .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    TUS_KOC_DATA_DIR=/data TUS_KOC_HOST=0.0.0.0 PORT=8000 \
    TUS_KOC_BEYIN_KAYNAK=/opt/avenoxbeyin TZ=Europe/Istanbul

# avenoxbeyin motoru: her kullanıcının kasası bunun install_v3.py'si ile kurulur.
COPY VERSION /opt/avenoxbeyin/VERSION
COPY scripts /opt/avenoxbeyin/scripts
COPY template /opt/avenoxbeyin/template

WORKDIR /app
COPY tus-koc/pyproject.toml tus-koc/README.md ./
COPY tus-koc/tus_koc ./tus_koc
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 koc && mkdir -p /data && chown koc /data

USER koc
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/saglik')"
CMD ["tus-koc"]
