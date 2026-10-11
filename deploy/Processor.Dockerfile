FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng && rm -rf /var/lib/apt/lists/* && useradd -m -u 10002 processor
WORKDIR /app
COPY requirements.processor.txt ./
RUN pip install --no-cache-dir -r requirements.processor.txt
COPY worker/__init__.py worker/config.py worker/processor_service.py worker/parser_child.py worker/extraction.py worker/export.py worker/resource_limits.py worker/
COPY data/taxonomy.json data/
COPY web/public/brand/JetBrainsMono-Regular.ttf web/public/brand/JetBrainsMono-Bold.ttf web/public/brand/
USER 10002:10002
ENV PROCESSOR_BIND=0.0.0.0 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TESSERACT_CMD=tesseract OMP_THREAD_LIMIT=2
CMD ["python", "-m", "worker.processor_service"]
