"""Logs structurés avec correlationId + documentId obligatoires."""
import logging
import uuid


def new_correlation_id() -> str:
    return str(uuid.uuid4())


class _ContextAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        cid = self.extra.get("correlationId")
        did = self.extra.get("documentId")
        return f"[correlationId={cid}][documentId={did}] {msg}", kwargs


def get_logger(correlation_id=None, document_id=None) -> logging.LoggerAdapter:
    logger = logging.getLogger("pipeline")
    logger.setLevel(logging.INFO)
    return _ContextAdapter(logger, {"correlationId": correlation_id, "documentId": document_id})
