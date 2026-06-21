"""Envoi de messages vers la queue Service Bus."""
import os
import json

from azure.servicebus import ServiceBusClient, ServiceBusMessage

QUEUE_NAME = os.environ.get("SERVICE_BUS_QUEUE", "documents")


def _conn():
    return (os.environ.get("ServiceBusConnection")
            or os.environ.get("SERVICE_BUS_CONNECTION_STRING"))


def publish_message(message: dict):
    conn = _conn()
    if not conn:
        raise RuntimeError("Connection string Service Bus absente")
    with ServiceBusClient.from_connection_string(conn) as client:
        with client.get_queue_sender(queue_name=QUEUE_NAME) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(message)))
