# Nova als Cloud-Dienst - laeuft rund um die Uhr, auch wenn dein PC aus ist.
# Anleitung: cloud/ANLEITUNG.md (Render kostenlos, oder eigener Server mit cloud/server-installieren.sh)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NOVA_CLOUD=1 \
    PORT=8765

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && pip install telethon

COPY . .
RUN useradd -m -u 1000 nova && mkdir -p /app/data /app/logs /app/workspace && chown -R nova /app
USER nova

EXPOSE 8765
CMD ["sh", "cloud/start.sh"]
