from __future__ import annotations

import json
from collections.abc import Sequence

# pyrefly: ignore [missing-import]
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
# pyrefly: ignore [missing-import]
from langchain_google_genai import ChatGoogleGenerativeAI

from app import config


def _messages_to_brief_text(messages: Sequence[BaseMessage], max_chars: int) -> str:
    parts: list[str] = []
    for m in messages:
        role = m.type if hasattr(m, "type") else m.__class__.__name__
        c = getattr(m, "content", "")
        if not isinstance(c, str):
            c = json.dumps(c, default=str)
        parts.append(f"[{role}] {c[:2000]}")
    out = "\n".join(parts)
    if len(out) > max_chars:
        return out[:max_chars] + "\n…(truncated for summarizer input)"
    return out


def merge_rolling_summary(prior: str, delta: str) -> str:
    prior = (prior or "").strip()
    delta = (delta or "").strip()
    if not prior:
        return delta
    if not delta:
        return prior
    merged = f"{prior}\n\n--- Updated ---\n{delta}"
    cap = getattr(config, "SUMMARY_MAX_CHARS", 8000)
    if len(merged) > cap:
        return merged[:cap] + "…"
    return merged


def generate_conversation_summary(
    old_slice: Sequence[BaseMessage],
    prior_summary: str,
) -> str:
    """
    LLM merges prior_summary with a digest of older messages (user goals, SQL topics, decisions).
    """
    if not old_slice and not prior_summary:
        return ""
    brief = _messages_to_brief_text(old_slice, max_chars=16000)
    if not brief.strip() and not prior_summary:
        return prior_summary or ""

    key = (config.SUMMARY_GEMINI_API_KEY or "").strip()
    if not key:
        return merge_rolling_summary(
            prior_summary,
            f"(Summary skipped: no SUMMARY_GEMINI_API_KEY) Transcript digest chars={len(brief)}",
        )

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=key,
        temperature=0,
    )
    prompt = f"""You maintain a rolling summary of an analytics / SQL assistant chat.

Prior summary (may be empty):
{prior_summary or "(none)"}

New older messages to fold in (may include digested tool output):
{brief}

Write an UPDATED summary that preserves:
- user goals and follow-ups
- database / SQL topics discussed
- important decisions or assumptions
- unresolved tasks
- business or schema context

Rules: concise bullet-style paragraphs; no chain-of-thought; max ~1200 words.
"""
    try:
        resp = llm.invoke(prompt)
        text = getattr(resp, "content", str(resp))
        if isinstance(text, list):
            text = " ".join(
                x.get("text", "") if isinstance(x, dict) else str(x) for x in text
            )
        text = (text or "").strip()
        cap = getattr(config, "SUMMARY_MAX_CHARS", 8000)
        if len(text) > cap:
            text = text[:cap] + "…"
        return text
    except Exception as e:
        return merge_rolling_summary(
            prior_summary,
            f"(Summary generation failed: {e!s})",
        )


def generate_global_memory_summary(prior_summary: str, chat_transcript: str) -> str:
    """
    Merge prior cross-chat memory with a full chat transcript into one concise summary.

    Keeps stable behavioral patterns; drops one-off numbers and temporary details.
    """
    prior = (prior_summary or "").strip()
    transcript = (chat_transcript or "").strip()
    if not transcript and not prior:
        return ""
    if not transcript:
        return prior

    cap = int(getattr(config, "GLOBAL_SUMMARY_MAX_CHARS", 8000) or 8000)
    if len(transcript) > 16000:
        transcript = transcript[:16000] + "\n…(transcript truncated)"

    key = (config.SUMMARY_GEMINI_API_KEY or config.GEMINI_API_KEY or "").strip()
    if not key:
        return merge_rolling_summary(
            prior,
            "(Global memory merge skipped: no GEMINI API key)",
        )

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=key,
        temperature=0,
    )
    prompt = f"""You maintain ONE evolving long-term memory for a single analytics user of a SQL assistant.

Existing long-term memory (may be empty):
{prior or "(none)"}

Chat transcript to fold in (completed conversation):
{transcript}

Write an UPDATED long-term memory summary that:
- Preserves stable patterns: preferred response style, recurring topics (sales, inventory, trends), typical question style, tables/metrics they often use.
- Drops temporary details: specific row counts, one-off dates, exact SQL, chart numbers from this chat unless they define a lasting preference.
- Uses short bullet points; max ~400 words.
- Does NOT include chain-of-thought.

Example style:
* User prefers concise analytical responses.
* Frequently asks sales and inventory questions.
* Uses short prompts.
* Often performs trend analysis.
"""
    try:
        resp = llm.invoke(prompt)
        text = getattr(resp, "content", str(resp))
        if isinstance(text, list):
            text = " ".join(
                x.get("text", "") if isinstance(x, dict) else str(x) for x in text
            )
        text = (text or "").strip()
        if len(text) > cap:
            text = text[:cap] + "…"
        return text
    except Exception as e:
        return merge_rolling_summary(
            prior,
            f"(Global memory merge failed: {e!s})",
        )


def extract_user_assistant_snippets(messages: Sequence[BaseMessage], max_msgs: int = 24) -> str:
    """Lightweight text for structured extraction (skip heavy tool bodies)."""
    lines: list[str] = []
    for m in messages[-max_msgs:]:
        if isinstance(m, HumanMessage):
            c = m.content if isinstance(m.content, str) else str(m.content)
            lines.append(f"user: {c[:1500]}")
        elif isinstance(m, AIMessage):
            c = m.content if isinstance(m.content, str) else str(m.content)
            if c.strip():
                lines.append(f"assistant: {c[:1500]}")
    return "\n".join(lines)
