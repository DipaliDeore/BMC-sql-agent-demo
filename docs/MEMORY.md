# Hybrid conversation memory

## Overview

When `HYBRID_MEMORY_ENABLED=true`, the SQL agent:

1. **Does not** change LangGraph checkpoints or rely on `body.messages`.
2. Builds an **LLM-only view** in `_prepend_system`: digest old `ToolMessage` payloads (before the latest user message), keep the last **`RECENT_MESSAGE_CAP`** messages, and prepend **structured memory** + **rolling summary** from Postgres table `bmcs_thread_memory` (or in-memory fallback when `POSTGRES_URI` is unset).

## Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `HYBRID_MEMORY_ENABLED` | `false` | Master switch |
| `RECENT_MESSAGE_CAP` | `30` | Max raw messages passed to the model (suffix of thread) |
| `SUMMARY_TRIGGER_MESSAGES` | `60` | Minimum total checkpoint messages before summarization may run |
| `MEMORY_SUMMARY_DEBOUNCE_MESSAGES` | `8` | Min new messages since last refresh before summarizing again |
| `MAX_CONTEXT_TOKENS_SOFT` | `120000` | Rough token estimate; if exceeded, digest more + tighter cap |
| `SUMMARY_MAX_CHARS` | `8000` | Stored / injected summary size cap |
| `STRUCTURED_MEMORY_JSON_MAX_CHARS` | `4000` | Injected JSON cap |
| `TOOL_DIGEST_MAX_CHARS` | `6000` | Per-tool digest body cap |

## Database

`init_chat_schema()` creates `bmcs_thread_memory` when Postgres is configured:

- `thread_id` (text, PK) — same as LangGraph `conversation_id`
- `conversation_summary` — rolling text
- `structured_memory` — JSONB
- `last_summarized_at_message_count` — debounce cursor (total message count snapshot after refresh)

## Operational notes

- Summarization calls **Gemini** (`gemini-2.5-flash-lite`); requires `GEMINI_API_KEY`.
- The **latest** `RECENT_MESSAGE_CAP` messages are never fed into the summarizer input (only the older prefix).
- Streaming (`/api/query/stream`) and sync (`generate_and_execute_with_tools`) both call `maybe_refresh_thread_memory_after_turn` after a graph run.

## Modules

- `app/memory/trim.py` — recent window + last human index
- `app/memory/tool_digest.py` — tabular tool JSON digests
- `app/memory/tokens.py` — rough token estimate
- `app/memory/summary.py` — rolling summary LLM
- `app/memory/structured.py` — structured memory LLM
- `app/memory/pipeline.py` — orchestration + logging
- `app/thread_memory.py` — persistence
