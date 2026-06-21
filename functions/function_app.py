"""
Azure Functions - Modèle de programmation Python v2.

Pipeline événementiel :
  1. blob_uploaded        : Blob Trigger -> publie un message Service Bus + notif UPLOADED
  2. process_document     : Service Bus Trigger -> IA tagging + Cosmos + notif PROCESSED
  3. dlq_alert            : Service Bus DLQ Trigger -> status ERROR + notif ERROR
  4. negotiate            : HTTP -> handshake SignalR pour le client React
"""

import json
import logging
from datetime import datetime, timezone

import azure.functions as func

from shared.logging_utils import get_logger, new_correlation_id
from shared.cosmos_client import get_document, upsert_status, set_error
from shared.signalr_client import notify, negotiate_info
from shared.ai_tagging import generate_tags
from shared.servicebus_client import publish_message, QUEUE_NAME

app = func.FunctionApp()


# ---------------------------------------------------------------------------
# 1. BLOB TRIGGER : un fichier arrive dans input/
# ---------------------------------------------------------------------------
@app.blob_trigger(arg_name="blob", path="input/{name}", connection="AzureWebJobsStorage")
def blob_uploaded(blob: func.InputStream):
    correlation_id = new_correlation_id()
    blob_name = blob.name                      # ex: "input/123_cv_amine_azure.pdf"
    file_name = blob_name.split("/")[-1]       # ex: "123_cv_amine_azure.pdf"
    document_id = file_name.split("_")[0]      # ex: "123"  (convention <id>_<nom>)
    size = blob.length or 0

    log = get_logger(correlation_id, document_id)
    log.info(json.dumps({"step": "BLOB_TRIGGER", "status": "RECEIVED",
                         "blobName": blob_name, "size": size}))

    message = {
        "documentId": document_id,
        "fileName": file_name,
        "blobName": blob_name,
        "size": size,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "correlationId": correlation_id,
    }

    try:
        upsert_status(document_id, "QUEUED",
                      extra={"fileName": file_name, "blobName": blob_name, "size": size})
        publish_message(message)
        notify(document_id, "UPLOADED", "Fichier reçu")
        log.info(json.dumps({"step": "BLOB_TRIGGER", "status": "QUEUED"}))
    except Exception as e:
        log.error(json.dumps({"step": "BLOB_TRIGGER", "status": "ERROR", "error": str(e)}))
        raise


# ---------------------------------------------------------------------------
# 2. SERVICE BUS TRIGGER : traitement IA
#    Toute exception => message abandonné => redélivré => DLQ après max_delivery_count
# ---------------------------------------------------------------------------
@app.service_bus_queue_trigger(arg_name="msg", queue_name=QUEUE_NAME,
                               connection="ServiceBusConnection")
def process_document(msg: func.ServiceBusMessage):
    # a) message mal formé -> on lève -> DLQ
    try:
        body = json.loads(msg.get_body().decode("utf-8"))
    except Exception as e:
        logging.error(json.dumps({"step": "SB_PROCESS", "status": "BAD_MESSAGE", "error": str(e)}))
        raise

    document_id = body.get("documentId")
    correlation_id = body.get("correlationId") or new_correlation_id()
    log = get_logger(correlation_id, document_id)
    log.info(json.dumps({"step": "SB_PROCESS", "status": "START"}))

    # b) documentId manquant -> DLQ
    if not document_id:
        log.error(json.dumps({"step": "SB_PROCESS", "status": "ERROR", "error": "documentId manquant"}))
        raise ValueError("documentId manquant")

    # c) document introuvable -> DLQ
    doc = get_document(document_id)
    if doc is None:
        log.error(json.dumps({"step": "SB_PROCESS", "status": "ERROR", "error": "Document introuvable"}))
        raise ValueError(f"Document {document_id} introuvable")

    # PROCESSING (envoyé tôt : on voit toujours la tentative à l'écran,
    # y compris pour un retry qui finira en erreur)
    upsert_status(document_id, "PROCESSING")
    notify(document_id, "PROCESSING", "Traitement IA en cours")

    # d) fichier vide -> DLQ
    if int(body.get("size", 0)) == 0:
        # on mémorise la raison réelle : la DLQ ne verra que "MaxDeliveryCountExceeded"
        upsert_status(document_id, "PROCESSING", extra={"lastErrorReason": "Fichier vide (0 octet)"})
        log.error(json.dumps({"step": "SB_PROCESS", "status": "ERROR", "error": "Fichier vide"}))
        raise ValueError("Fichier vide")

    # IA tagging (avec fallback interne par règles)
    tags = generate_tags(body.get("fileName", ""), correlation_id, document_id)

    processed_at = datetime.now(timezone.utc).isoformat()
    upsert_status(document_id, "PROCESSED",
                  extra={"tags": tags, "processedAt": processed_at})
    notify(document_id, "PROCESSED", "Tagging terminé", tags=tags)
    log.info(json.dumps({"step": "SB_PROCESS", "status": "SUCCESS", "tags": tags}))


# ---------------------------------------------------------------------------
# 3. DLQ TRIGGER : surveillance de la Dead Letter Queue
# ---------------------------------------------------------------------------
@app.service_bus_queue_trigger(arg_name="msg",
                               queue_name=f"{QUEUE_NAME}/$DeadLetterQueue",
                               connection="ServiceBusConnection")
def dlq_alert(msg: func.ServiceBusMessage):
    correlation_id = new_correlation_id()
    document_id = None
    try:
        body = json.loads(msg.get_body().decode("utf-8"))
        document_id = body.get("documentId")
        correlation_id = body.get("correlationId") or correlation_id
    except Exception:
        body = {}

    log = get_logger(correlation_id, document_id)
    sb_reason = (getattr(msg, "dead_letter_reason", None)
                 or getattr(msg, "dead_letter_error_description", None)
                 or "Message envoyé en DLQ après plusieurs échecs")
    error_at = datetime.now(timezone.utc).isoformat()

    # raison métier réelle si on l'a mémorisée, sinon raison technique Service Bus
    reason = sb_reason
    if document_id:
        doc = get_document(document_id)
        if doc and doc.get("lastErrorReason"):
            reason = doc["lastErrorReason"]

    log.error(json.dumps({"step": "DLQ_ALERT", "status": "ERROR", "reason": reason}))

    if document_id:
        set_error(document_id, reason, error_at)
        notify(document_id, "ERROR", reason)


# ---------------------------------------------------------------------------
# 4. NEGOTIATE : handshake SignalR pour le client React (mode serverless)
# ---------------------------------------------------------------------------
@app.route(route="negotiate", methods=["GET", "POST", "OPTIONS"],
           auth_level=func.AuthLevel.ANONYMOUS)
def negotiate(req: func.HttpRequest) -> func.HttpResponse:
    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=cors)

    info = negotiate_info()
    return func.HttpResponse(json.dumps(info), mimetype="application/json",
                             headers=cors, status_code=200)
