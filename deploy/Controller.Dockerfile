FROM python:3.12-slim-bookworm
RUN useradd -m -u 10001 controller
WORKDIR /app
COPY requirements.controller.txt ./
RUN pip install --no-cache-dir -r requirements.controller.txt
COPY worker/__init__.py worker/main.py worker/process_job.py worker/config.py worker/errors.py worker/
RUN mkdir -p runtime/storage && chown -R controller:controller runtime
USER 10001:10001
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 STORAGE_DIR=/app/runtime/storage
CMD ["python", "-m", "worker.main"]
