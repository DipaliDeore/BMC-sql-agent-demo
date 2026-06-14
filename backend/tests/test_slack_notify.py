from unittest.mock import MagicMock, patch

from app.services.slack_notify import (
    _build_slack_payload,
    _slack_configured,
    send_negative_feedback_to_slack,
)


def test_build_slack_payload_includes_core_fields():
    entry = {
        "label": "NEGATIVE_FEEDBACK",
        "timestamp": "2026-06-11T12:00:00",
        "query": "Predict next 3 months sales",
        "sql": "SELECT 1",
        "ai_response": "Could not forecast.",
        "session_id": "sess_abc",
    }
    payload = _build_slack_payload(entry)
    assert payload["text"].startswith("SQL Agent thumbs down")
    blocks = payload["blocks"]
    combined = " ".join(
        b.get("text", {}).get("text", "") for b in blocks if b.get("type") == "section"
    )
    assert "Predict next 3 months sales" in combined
    assert "SELECT 1" in combined
    assert "sess_abc" in combined


@patch("app.services.slack_notify._slack_configured", return_value=False)
def test_send_skipped_when_not_configured(mock_cfg):
    assert send_negative_feedback_to_slack({"query": "x"}) is False


@patch("app.services.slack_notify._slack_configured", return_value=True)
@patch("app.services.slack_notify.config.SLACK_FEEDBACK_WEBHOOK_URL", "https://hooks.slack.com/test")
@patch("urllib.request.urlopen")
def test_send_success(mock_urlopen, mock_cfg):
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    ok = send_negative_feedback_to_slack(
        {
            "query": "test question",
            "sql": "SELECT 1",
            "timestamp": "2026-01-01",
            "session_id": "s1",
        }
    )
    assert ok is True
    mock_urlopen.assert_called_once()
