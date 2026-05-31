/**
 * agent.js - API Layer
 * --------------------
 * Handles all API communication with the FastAPI backend.
 */

import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const DEFAULT_ERROR_MESSAGE =
  "Hmm, something went wrong. Could you try again in a moment?";

export function getApiErrorMessage(error) {
  if (error?.name === "AbortError") {
    return "Request cancelled.";
  }
  if (!error?.response?.data) {
    const msg = error?.message || "";
    if (msg.includes("Network Error")) {
      return "I can't reach the server right now — is the backend running?";
    }
    if (msg.trim()) return msg;
    return DEFAULT_ERROR_MESSAGE;
  }
  const d = error.response.data.detail;
  if (typeof d === "string" && d.trim()) return d;
  if (Array.isArray(d) && d.length > 0) {
    const first = d[0];
    if (typeof first === "string") return first;
    if (first && typeof first.msg === "string") return first.msg;
  }
  return DEFAULT_ERROR_MESSAGE;
}

/**
 * Map UI messages to API `messages` (optional transcript on each query).
 */
export function mapMessagesForApi(messages) {
  if (!messages?.length) return null;
  return messages.map((m) => {
    if (m.role === "user") {
      return { role: "user", content: (m.content || "").trim() };
    }
    const text =
      (m.explanation || m.content || m.errorText || "").trim() ||
      "(assistant reply)";
    return { role: "assistant", content: text };
  });
}

export async function listChats() {
  const response = await axios.get(`${API_BASE_URL}/api/chats`);
  return response.data.chats || [];
}

export async function createChat(title) {
  const response = await axios.post(`${API_BASE_URL}/api/chats`, {
    title: title ?? null,
  });
  return response.data;
}

/** Merge closing chat into cross-chat global memory. */
export async function mergeChatIntoGlobalMemory(chatId) {
  const response = await axios.post(`${API_BASE_URL}/api/memory/merge-chat`, {
    chat_id: chatId,
  });
  return response.data;
}

/** Merge all chats not yet folded into global memory (skip active chat). */
export async function mergePendingGlobalMemory(excludeChatId = null) {
  const response = await axios.post(`${API_BASE_URL}/api/memory/merge-pending`, {
    exclude_chat_id: excludeChatId ?? null,
  });
  return response.data;
}

/** Best-effort merge when the tab closes (sendBeacon; may not always complete). */
export function beaconMergeChatIntoGlobalMemory(chatId) {
  if (!chatId || typeof navigator.sendBeacon !== "function") return false;
  const body = JSON.stringify({ chat_id: chatId });
  const blob = new Blob([body], { type: "application/json" });
  return navigator.sendBeacon(`${API_BASE_URL}/api/memory/merge-chat`, blob);
}

export async function getChatMessages(chatId) {
  const response = await axios.get(
    `${API_BASE_URL}/api/chats/${chatId}/messages`,
  );
  return response.data.messages || [];
}

export async function renameChat(chatId, title) {
  const response = await axios.patch(`${API_BASE_URL}/api/chats/${chatId}`, {
    title,
  });
  return response.data;
}

export async function deleteChat(chatId) {
  await axios.delete(`${API_BASE_URL}/api/chats/${chatId}`);
}

/**
 * POST /api/query/stream — SSE over fetch + ReadableStream (do not use axios).
 *
 * @param {AbortSignal} [signal] — abort to cancel in-flight stream (Stop / unmount)
 */
export async function streamQuery(
  question,
  conversationId,
  preference = "AUTO",
  messages = null,
  handlers = {},
  images = null,
  signal = undefined,
) {
  const { onEvent } = handlers;
  const body = { question, preference: preference || "AUTO" };
  if (conversationId) body.conversation_id = conversationId;
  if (messages?.length) body.messages = messages;
  if (images?.length) {
    body.images = images.map(({ media_type, data_base64 }) => ({
      media_type: media_type || "image/png",
      data_base64,
    }));
  }

  const res = await fetch(`${API_BASE_URL}/api/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("No response body to read.");
  }

  const decoder = new TextDecoder();
  let carry = "";

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        throw new DOMException("Aborted", "AbortError");
      }

      const { done, value } = await reader.read();
      if (done) break;
      carry += decoder.decode(value, { stream: true });

      const blocks = carry.split("\n\n");
      carry = blocks.pop() ?? "";

      for (const block of blocks) {
        const lines = block.split("\n");
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) continue;
          const jsonStr = trimmed.slice(5).trim();
          if (!jsonStr) continue;
          let evt;
          try {
            evt = JSON.parse(jsonStr);
          } catch {
            continue;
          }
          if (onEvent && evt?.type) onEvent(evt);
        }
      }
    }
  } catch (err) {
    try {
      await reader.cancel();
    } catch {
      /* ignore */
    }
    throw err;
  }
}

function getSessionId() {
  let sid = window.localStorage.getItem("session_id");
  if (!sid) {
    sid = `sess_${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem("session_id", sid);
  }
  return sid;
}

export async function submitFeedback(
  query,
  response,
  feedback,
  { sql = "" } = {},
) {
  if (feedback !== "up" && feedback !== "down") {
    throw new Error("submitFeedback: feedback must be 'up' or 'down'");
  }
  const payload = {
    query,
    response,
    feedback,
    sql,
    session_id: getSessionId(),
  };
  const res = await axios.post(`${API_BASE_URL}/feedback`, payload);
  return res.data;
}
