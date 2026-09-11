FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY web ./web

RUN mkdir -p /data/media /data/logs

EXPOSE 8000

CMD ["sh", "-c", "python -m app.worker & exec uvicorn app.combined:app --host 0.0.0.0 --port ${PORT:-8000}"]
