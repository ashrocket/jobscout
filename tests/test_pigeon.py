from unittest.mock import patch, MagicMock
from jobscout.integrations.pigeon import send_document, send_question, send_message, poll_reply


def _mock_post(status_code=200, json_data=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {"ok": True, "id": "msg-123"}
    mock.raise_for_status = MagicMock()
    return mock


@patch("jobscout.integrations.pigeon.httpx.post")
def test_send_document(mock_post):
    mock_post.return_value = _mock_post(json_data={"ok": True, "id": "msg-abc"})
    msg_id = send_document(title="Test Report", html="<h1>Jobs</h1>")
    assert msg_id == "msg-abc"
    call_args = mock_post.call_args
    body = call_args[1]["json"]
    assert body["type"] == "document"
    assert body["title"] == "Test Report"


@patch("jobscout.integrations.pigeon.httpx.post")
def test_send_question(mock_post):
    mock_post.return_value = _mock_post(json_data={"ok": True, "id": "msg-q1"})
    msg_id = send_question(title="Apply?", body="VP Eng at Acme — apply?")
    assert msg_id == "msg-q1"
    call_args = mock_post.call_args
    body = call_args[1]["json"]
    assert body["type"] == "question"


@patch("jobscout.integrations.pigeon.httpx.get")
def test_poll_reply_found(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": {"replied": True, "reply": "yes apply"}}
    mock_get.return_value = mock_resp
    reply = poll_reply("msg-q1")
    assert reply == "yes apply"


@patch("jobscout.integrations.pigeon.httpx.get")
def test_poll_reply_not_yet(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "reply": None}
    mock_get.return_value = mock_resp
    reply = poll_reply("msg-q1")
    assert reply is None
