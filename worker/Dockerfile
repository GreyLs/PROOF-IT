FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng && rm -rf /var/lib/apt/lists/* && useradd -m -u 10001 fsp
WORKDIR /app
COPY requirements.worker.txt ./
RUN pip install --no-cache-dir -r requirements.worker.txt
COPY worker/ worker/
COPY data/taxonomy.json data/
COPY web/public/brand/JetBrainsMono-Regular.ttf web/public/brand/JetBrainsMono-Bold.ttf web/public/brand/
RUN mkdir -p runtime/storage && chown -R fsp:fsp /app
USER fsp
ENV STORAGE_DIR=/app/runtime/storage PYTHONUNBUFFERED=1 TESSERACT_CMD=tesseract
CMD ["python", "-m", "worker.main"]
