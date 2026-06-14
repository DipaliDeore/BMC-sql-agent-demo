"""
slack_notify.py — Post thumbs-down feedback to a Slack Incoming Webhook.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from typing import Any

from app import config

_MAX_BLOCK_CHARS = 2800


def _truncate(text: str, limit: int = _MAX_BLOCK_CHARS) -> str:
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _slack_configured() -> bool:
    url = getattr(config, "SLACK_FEEDBACK_WEBHOOK_URL", "") or ""
    enabled = getattr(config, "SLACK_FEEDBACK_ENABLED", True)
    return bool(enabled and url.strip())


def _build_slack_payload(entry: dict[str, Any]) -> dict[str, Any]:
    label = entry.get("label") or "NEGATIVE_FEEDBACK"
    timestamp = entry.get("timestamp") or ""
    query = _truncate(str(entry.get("query") or ""), 1500)
    sql = _truncate(str(entry.get("sql") or ""), 1500)
    response = _truncate(str(entry.get("ai_response") or ""), 1200)
    session_id = str(entry.get("session_id") or "unknown")
    note = str(entry.get("note") or "").strip()

    lines = [
        f"*Label:* {label}",
        f"*Time:* {timestamp}",
        f"*Session:* `{session_id}`",
    ]
    if note:
        lines.append(f"*Note:* {note}")

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "👎 SQL Agent — thumbs down", "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Question*\n{_truncate(query, 2000)}",
            },
        },
    ]

    if sql:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*SQL*\n```{sql}```",
                },
            }
        )

    if response:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Assistant response*\n{_truncate(response, 2000)}",
                },
            }
        )

    meta = entry.get("metadata")
    if isinstance(meta, dict) and meta:
        try:
            meta_text = _truncate(
                json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True),
                1200,
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"*Metadata*\n```{meta_text}```"},
                }
            )
        except (TypeError, ValueError):
            pass

    return {
        "text": f"SQL Agent thumbs down: {query[:120]}",
        "blocks": blocks,
    }


def send_negative_feedback_to_slack(entry: dict[str, Any]) -> bool:
    """
    POST feedback context to Slack. Returns True on success, False if skipped or failed.
    Never raises — failures are logged only.
    """
    if not _slack_configured():
        return False

    url = config.SLACK_FEEDBACK_WEBHOOK_URL.strip()
    payload = _build_slack_payload(entry)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = float(getattr(config, "SLACK_FEEDBACK_TIMEOUT_SECONDS", 5.0))

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True
        print(f"[SlackNotify] Unexpected status from webhook")
        return False
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        print(f"[SlackNotify] HTTP error {exc.code}: {exc.reason} {body}")
        return False
    except Exception as exc:
        print(f"[SlackNotify] Failed to post: {type(exc).__name__}: {exc}")
        return False


def notify_negative_feedback_async(entry: dict[str, Any]) -> None:
    """Fire-and-forget Slack notification so POST /feedback stays fast."""
    if not _slack_configured():
        return

    def _run() -> None:
        send_negative_feedback_to_slack(entry)

    threading.Thread(target=_run, daemon=True).start()
