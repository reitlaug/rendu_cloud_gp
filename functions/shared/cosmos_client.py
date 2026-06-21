"""Accès Cosmos DB (API NoSQL). Partition key = /id."""
import os

from azure.cosmos import CosmosClient, PartitionKey, exceptions

_container = None


def _get_container():
    global _container
    if _container is None:
        endpoint = os.environ["COSMOS_ENDPOINT"]
        key = os.environ["COSMOS_KEY"]
        db_name = os.environ.get("COSMOS_DATABASE", "documents")
        container_name = os.environ.get("COSMOS_CONTAINER", "documents")

        client = CosmosClient(endpoint, credential=key)
        db = client.create_database_if_not_exists(db_name)
        _container = db.create_container_if_not_exists(
            id=container_name,
            partition_key=PartitionKey(path="/id"),
        )
    return _container


def get_document(document_id: str):
    try:
        return _get_container().read_item(item=document_id, partition_key=document_id)
    except exceptions.CosmosResourceNotFoundError:
        return None


def upsert_status(document_id: str, status: str, extra: dict = None):
    c = _get_container()
    try:
        doc = c.read_item(item=document_id, partition_key=document_id)
    except exceptions.CosmosResourceNotFoundError:
        doc = {"id": document_id}
    doc["status"] = status
    if extra:
        doc.update(extra)
    c.upsert_item(doc)
    return doc


def set_error(document_id: str, error_message: str, error_at: str):
    c = _get_container()
    try:
        doc = c.read_item(item=document_id, partition_key=document_id)
    except exceptions.CosmosResourceNotFoundError:
        doc = {"id": document_id}
    doc["status"] = "ERROR"
    doc["errorMessage"] = error_message
    doc["errorAt"] = error_at
    c.upsert_item(doc)
    return doc
