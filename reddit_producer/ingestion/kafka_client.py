# ingestion/kafka_client.py

import os
import json
import time
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
print("BOOTSTRAP =", KAFKA_BOOTSTRAP)

producer = None

def get_producer():
    global producer

    if producer:
        return producer

    for _ in range(10):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8")
            )
            print("Kafka producer connected.")
            return producer
        except NoBrokersAvailable:
            print("Kafka not ready, retrying...")
            time.sleep(5)

    raise Exception("Kafka broker not available")
