FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.lock.txt requirements.forecasting.txt requirements.intelligence.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt -r requirements.forecasting.txt -r requirements.intelligence.txt && useradd -u 10005 intelligence
COPY intelligence/ intelligence/
COPY ml_time_forecasting/ ml_time_forecasting/
COPY worker/__init__.py worker/config.py worker/workbench.py worker/
COPY data/taxonomy.json data/taxonomy.json
USER 10005:10005
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 INTELLIGENCE_HOST=0.0.0.0
CMD ["python", "-m", "intelligence.service"]
