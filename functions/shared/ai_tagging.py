"""Tagging IA via Azure OpenAI, avec fallback par règles si l'appel échoue."""
import os
import re
import json

from shared.logging_utils import get_logger

PROMPT = (
    "Analyse le nom de fichier suivant et génère entre 3 et 8 tags courts en français.\n"
    "Nom du fichier : {file_name}\n\n"
    "Retourne uniquement un tableau JSON de chaînes."
)


def _fallback_tags(file_name: str):
    base = re.sub(r"\.[^.]+$", "", file_name).lower()
    parts = re.split(r"[_\-\s.]+", base)
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    tags = [p for p in parts if len(p) > 2 and not p.isdigit()]
    if ext:
        tags.append(ext)
    seen = []
    for t in tags:
        if t not in seen:
            seen.append(t)
    return seen[:8] or ["document"]


def generate_tags(file_name: str, correlation_id=None, document_id=None):
    log = get_logger(correlation_id, document_id)

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")

    if not (endpoint and api_key and deployment):
        log.warning(json.dumps({"step": "AI_TAGGING", "status": "FALLBACK",
                                "reason": "config Azure OpenAI absente"}))
        return _fallback_tags(file_name)

    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01"),
        )
        resp = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": PROMPT.format(file_name=file_name)}],
            temperature=0.3,
            max_tokens=120,
        )
        content = resp.choices[0].message.content.strip()
        match = re.search(r"\[.*\]", content, re.S)
        raw = json.loads(match.group(0) if match else content)
        tags = [str(t).lower().strip() for t in raw if str(t).strip()][:8]
        log.info(json.dumps({"step": "AI_TAGGING", "status": "SUCCESS", "tags": tags}))
        return tags or _fallback_tags(file_name)
    except Exception as e:
        log.error(json.dumps({"step": "AI_TAGGING", "status": "FALLBACK", "error": str(e)}))
        return _fallback_tags(file_name)
