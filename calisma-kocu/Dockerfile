# Repo kökünden derlenir; sunucu avenoxbeyin'in scripts/ ve template/ klasörlerini kullanır:
#   docker build -f calisma-kocu/Dockerfile -t calisma-kocu .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    KOC_DATA_DIR=/data KOC_HOST=0.0.0.0 PORT=8000 \
    KOC_BEYIN_KAYNAK=/opt/avenoxbeyin TZ=Europe/Istanbul

# avenoxbeyin motoru: her kullanıcının kasası bunun install_v3.py'si ile kurulur.
COPY VERSION /opt/avenoxbeyin/VERSION
COPY scripts /opt/avenoxbeyin/scripts
COPY template /opt/avenoxbeyin/template

WORKDIR /app
COPY calisma-kocu/pyproject.toml calisma-kocu/README.md ./
COPY calisma-kocu/calisma_kocu ./calisma_kocu
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 koc && mkdir -p /data && chown koc /data

USER koc
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/saglik')"
CMD ["calisma-kocu"]
