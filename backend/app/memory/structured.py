from __future__ import annotations

import json
import re
from typing import Any

from app import config
# pyrefly: ignore [missing-import]
from langchain_google_genai import ChatGoogleGenerativeAI


def merge_structured_memory(prior: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Shallow merge; delta keys overwrite prior."""
    out = dict(prior or {})
    for k, v in (delta or {}).items():
        if v is not None and v != "" and v != []:
            out[k] = v
    return out


def _cap_json(obj: dict[str, Any], max_chars: int) -> dict[str, Any]:
    raw = json.dumps(obj, ensure_ascii=False, default=str)
    if len(raw) <= max_chars:
        return obj
    keys = list(obj.keys())
    while keys and len(json.dumps({k: obj[k] for k in keys}, default=str)) > max_chars:
        keys.pop()
    return {k: obj[k] for k in keys}


def extract_structured_memory(
    transcript_snippet: str,
    prior: dict[str, Any],
) -> dict[str, Any]:
    """
    LLM extracts small JSON facts: sql_dialect, business_context, user_preferences, etc.
    """
    key = (config.SUMMARY_GEMINI_API_KEY or "").strip()
    if not key or not transcript_snippet.strip():
        return {}

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=key,
        temperature=0,
    )
    prompt = f"""From this chat snippet, extract JSON ONLY (no markdown) with keys if known, else omit:
{{
  "sql_dialect": "mysql|tidb|unknown",
  "business_context": "short phrase",
  "user_preferences": {{}},
  "selected_tables": [],
  "notes": "short"
}}

Prior JSON (merge; new snippet wins on conflicts):
{json.dumps(prior, ensure_ascii=False, default=str)}

Snippet:
{transcript_snippet[:12000]}
"""
    try:
        resp = llm.invoke(prompt)
        text = getattr(resp, "content", str(resp))
        if isinstance(text, list):
            text = " ".join(
                x.get("text", "") if isinstance(x, dict) else str(x) for x in text
            )
        text = (text or "").strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        data = json.loads(m.group(0))
        if not isinstance(data, dict):
            return {}
        merged = merge_structured_memory(prior, data)
        cap = getattr(config, "STRUCTURED_MEMORY_JSON_MAX_CHARS", 4000)
        return _cap_json(merged, cap)
    except Exception:
        return {}
