import httpx
from jobscout.config import read_credential, get_pigeon_project


def _instance_meta() -> dict:
    return {
        "model": "jobscout-pipeline",
        "session_id": "jobscout-hourly",
        "project": get_pigeon_project(),
        "source": "jobscout",
    }


def _base_url() -> str:
    return read_credential("pigeon-worker-url")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {read_credential('pigeon-api-key')}",
        "Content-Type": "application/json",
    }


def _post_message(payload: dict) -> str:
    payload["instance"] = _instance_meta()
    resp = httpx.post(f"{_base_url()}/api/messages", json=payload, headers=_headers(), timeout=30)
    resp.raise_for_status()
    body = resp.json()
    return body.get("data", {}).get("id") or body.get("id", "")


def send_document(title: str, html: str, priority: str = "normal") -> str:
    # Worker expects `html` (stored to R2); `body` is ignored for documents
    # and causes the push preview to contain raw markup. See
    # claudia-pigeon/server/src/routes/messages.ts:43.
    return _post_message({"type": "document", "title": title, "html": html, "priority": priority})


def send_question(title: str, body: str, priority: str = "urgent") -> str:
    return _post_message({"type": "question", "title": title, "body": body, "priority": priority})


def send_message(title: str, body: str, priority: str = "normal") -> str:
    return _post_message({"type": "message", "title": title, "body": body, "priority": priority})


def poll_reply(message_id: str) -> str | None:
    resp = httpx.get(f"{_base_url()}/api/replies/{message_id}", headers=_headers(), timeout=10)
    resp.raise_for_status()
    body = resp.json()
    data = body.get("data", body)
    if not data.get("replied"):
        return None
    return data.get("reply")
