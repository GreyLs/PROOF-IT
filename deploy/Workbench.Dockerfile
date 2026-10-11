FROM python:3.12-slim-bookworm
# Docker CLI connects only to the dedicated executor daemon, never to API pods.
RUN apt-get update && apt-get install -y --no-install-recommends docker.io ca-certificates && rm -rf /var/lib/apt/lists/* && useradd -u 10006 workbench
WORKDIR /app
COPY requirements.lock.txt requirements.intelligence.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt -r requirements.intelligence.txt
COPY worker/__init__.py worker/config.py worker/workbench.py worker/
USER 10006:10006
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 WORKBENCH_HOST=0.0.0.0
CMD ["python", "-m", "worker.workbench"]
