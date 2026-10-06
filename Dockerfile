# My Meal Plan – self-hosted weekly dinner planner
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data \
    PORT=3000 \
    PUID=1000 \
    PGID=1000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# The compiled stylesheet (app/static/css/app.css) and vendored JS/fonts are
# part of the source tree, so the image needs no Node.js or internet assets.
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && mkdir -p /data/uploads

VOLUME ["/data"]
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '3000'), timeout=4)" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
# A single worker on purpose: the dinner-reminder scheduler runs inside the app process.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
