# Tagger AI (run_task.py + tagger/) - jednorazowy task ECS: SQS -> DeepSeek -> DynamoDB
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY run_task.py .
COPY tagger/ tagger/

USER nobody
ENTRYPOINT ["python", "run_task.py"]
