FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir \
    praw \
    kafka-python \
    python-dotenv

CMD ["python", "-m", "ingestion.main"]
#CMD ["python", "-m", "reddit_producer.ingestion.main"]

