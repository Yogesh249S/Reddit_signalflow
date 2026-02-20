FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir \
    psycopg2-binary \
    kafka-python \
    vaderSentiment

CMD ["python", "-m", "processing.main_processor"]
