# Importer: API UM Warszawy -> wspólny schemat -> SQS (jednorazowy task ECS co 2 h)
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

USER nobody
ENTRYPOINT ["python", "main.py"]
