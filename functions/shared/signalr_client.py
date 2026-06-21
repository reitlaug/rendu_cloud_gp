"""
Client SignalR (mode Serverless) via l'API REST + JWT.
Auto-contenu : ne dépend pas de l'extension de binding (plus robuste en démo).
"""
import os
import json
import time
import logging
import urllib.request

import jwt  # PyJWT

HUB = os.environ.get("SIGNALR_HUB", "documents")


def _conn():
    return (os.environ.get("SignalRConnectionString")
            or os.environ.get("AzureSignalRConnectionString")
            or os.environ.get("SIGNALR_CONNECTION_STRING"))


def _parse(conn: str):
    parts = dict(p.split("=", 1) for p in conn.split(";") if "=" in p)
    return parts.get("Endpoint"), parts.get("AccessKey")


def _token(audience: str, key: str, user_id: str = None) -> str:
    payload = {"aud": audience, "exp": int(time.time()) + 3600}
    if user_id:
        payload["nameid"] = user_id
    return jwt.encode(payload, key, algorithm="HS256")


def negotiate_info() -> dict:
    """Renvoyé au client React : url du service + accessToken."""
    conn = _conn()
    endpoint, key = _parse(conn)
    client_url = f"{endpoint}/client/?hub={HUB}"
    return {"url": client_url, "accessToken": _token(client_url, key)}


def notify(document_id: str, status: str, message: str, tags=None):
    """Broadcast d'un événement sur le hub (target = 'documentUpdate')."""
    conn = _conn()
    if not conn:
        logging.warning("[SignalR] connection string absente, notif ignorée")
        return

    endpoint, key = _parse(conn)
    url = f"{endpoint}/api/v1/hubs/{HUB}"

    payload = {"documentId": document_id, "status": status, "message": message}
    if tags is not None:
        payload["tags"] = tags

    body = json.dumps({"target": "documentUpdate", "arguments": [payload]}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {_token(url, key)}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logging.warning(f"[SignalR] notify a échoué ({status} / {document_id}) : {e}")
