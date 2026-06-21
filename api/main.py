"""
API FastAPI : création de document, génération SAS (upload React), et relance (retry).
"""
import os
import json
import uuid
import logging
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

load_dotenv()  # charge le fichier .env (variables Cosmos / Service Bus / Storage)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.storage.blob import (
    BlobServiceClient, generate_blob_sas, BlobSasPermissions,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

# --- Config ----------------------------------------------------------------
COSMOS_ENDPOINT = os.environ["COSMOS_ENDPOINT"]
COSMOS_KEY = os.environ["COSMOS_KEY"]
COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "documents")
COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "documents")

SB_CONNECTION = os.environ["SERVICE_BUS_CONNECTION_STRING"]
SB_QUEUE = os.environ.get("SERVICE_BUS_QUEUE", "documents")

STORAGE_CONNECTION = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
INPUT_CONTAINER = os.environ.get("INPUT_CONTAINER", "input")

# --- Clients ---------------------------------------------------------------
_cosmos = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
_db = _cosmos.create_database_if_not_exists(COSMOS_DATABASE)
_container = _db.create_container_if_not_exists(
    id=COSMOS_CONTAINER, partition_key=PartitionKey(path="/id"))

_blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION)

app = FastAPI(title="Document Pipeline API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# --- Modèles ---------------------------------------------------------------
class CreateDocument(BaseModel):
    fileName: str


# --- Helpers ---------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc).isoformat()


def _new_correlation_id():
    return str(uuid.uuid4())


def _publish(message: dict):
    with ServiceBusClient.from_connection_string(SB_CONNECTION) as client:
        with client.get_queue_sender(queue_name=SB_QUEUE) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(message)))


# --- Endpoints -------------------------------------------------------------
@app.post("/documents")
def create_document(payload: CreateDocument):
    """Crée le document (status CREATED) et renvoie l'URL SAS d'upload."""
    document_id = str(uuid.uuid4().int)[:6]
    blob_name = f"{document_id}_{payload.fileName}"
    correlation_id = _new_correlation_id()

    doc = {
        "id": document_id,
        "fileName": payload.fileName,
        "blobName": f"{INPUT_CONTAINER}/{blob_name}",
        "status": "CREATED",
        "createdAt": _now(),
        "correlationId": correlation_id,
    }
    _container.upsert_item(doc)
    log.info(json.dumps({"correlationId": correlation_id, "documentId": document_id,
                         "step": "CREATE", "status": "CREATED"}))

    sas = generate_blob_sas(
        account_name=_blob_service.account_name,
        container_name=INPUT_CONTAINER,
        blob_name=blob_name,
        account_key=_blob_service.credential.account_key,
        permission=BlobSasPermissions(write=True, create=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    upload_url = f"{_blob_service.url}{INPUT_CONTAINER}/{blob_name}?{sas}"
    return {"documentId": document_id, "blobName": blob_name, "uploadUrl": upload_url}


@app.get("/documents/{document_id}")
def get_document(document_id: str):
    try:
        return _container.read_item(item=document_id, partition_key=document_id)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Document introuvable")


@app.post("/documents/{document_id}/retry")
def retry_document(document_id: str):
    """Republie un message Service Bus pour relancer le traitement."""
    try:
        doc = _container.read_item(item=document_id, partition_key=document_id)
    except exceptions.CosmosResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Document introuvable")

    correlation_id = _new_correlation_id()
    message = {
        "documentId": document_id,
        "fileName": doc.get("fileName"),
        "blobName": doc.get("blobName"),
        "size": doc.get("size", 1),
        "uploadedAt": _now(),
        "correlationId": correlation_id,
        "retry": True,
    }
    _publish(message)

    doc["status"] = "QUEUED"
    doc.pop("errorMessage", None)
    doc.pop("errorAt", None)
    _container.upsert_item(doc)

    log.info(json.dumps({"correlationId": correlation_id, "documentId": document_id,
                         "step": "RETRY", "status": "QUEUED"}))
    return {"documentId": document_id, "status": "QUEUED", "message": "Document relancé"}


@app.get("/health")
def health():
    return {"status": "ok"}
