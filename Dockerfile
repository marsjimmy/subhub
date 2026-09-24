FROM python:3.12-slim

LABEL org.opencontainers.image.title="subhub" \
      org.opencontainers.image.version="0.2.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MEDIA_DIR=/media \
    DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .

# ddddocr 的 onnxruntime 需要 libgomp1;清华源对 ddddocr 限流(403),改用官方源
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --timeout 120 -r requirements.txt \
    && rm -rf /root/.cache/pip

COPY app ./app

# 非 root 运行
RUN useradd --create-home --uid 1000 subhub && mkdir -p /media /data && chown subhub:subhub /data
USER subhub

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
