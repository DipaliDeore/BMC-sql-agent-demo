/**
 * agent.js - API Layer
 * --------------------
 * Handles all API communication with the FastAPI backend.
 */

import axios from "axios";

const API_BASE_URL = "http://localhost:8000";

const DEFAULT_ERROR_MESSAGE =
  "Hmm, something went wrong. Could you try again in a moment?";

export function getApiErrorMessage(error) {
  if (!error?.response?.data) {
    return error?.message?.includes("Network Error")
      ? "I can't reach the server right now — is the backend running?"
      : DEFAULT_ERROR_MESSAGE;
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
      (m.explanation || m.content || m.errorText || "").trim() || "(assistant reply)";
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

export async function getChatMessages(chatId) {
  const response = await axios.get(`${API_BASE_URL}/api/chats/${chatId}/messages`);
  return response.data.messages || [];
}

export async function renameChat(chatId, title) {
  const response = await axios.patch(`${API_BASE_URL}/api/chats/${chatId}`, { title });
  return response.data;
}

export async function deleteChat(chatId) {
  await axios.delete(`${API_BASE_URL}/api/chats/${chatId}`);
}

/**
 * @param {string} question
 * @param {string} [conversationId]
 * @param {string} [preference]
 * @param {Array<{role:string,content:string}>|null} [messages] prior turns for the request body
 */
export async function sendQuery(question, conversationId, preference = "AUTO", messages = null) {
  const body = { question, preference };
  if (conversationId) body.conversation_id = conversationId;
  if (messages?.length) body.messages = messages;
  const response = await axios.post(`${API_BASE_URL}/api/query`, body);
  return response.data;
}

/**
 * POST /api/query/stream — SSE over fetch + ReadableStream (do not use axios).
 *
 * @param {string} question
 * @param {string} [conversationId]
 * @param {string} [preference]
 * @param {Array<{role:string,content:string}>|null} [messages]
 * @param {{ onEvent?: (e: { type: string, content: unknown }) => void }} [handlers]
 * @returns {Promise<void>}
 */
export async function streamQuery(
  question,
  conversationId,
  preference = "AUTO",
  messages = null,
  handlers = {}
) {
  const { onEvent } = handlers;
  const body = { question, preference: preference || "AUTO" };
  if (conversationId) body.conversation_id = conversationId;
  if (messages?.length) body.messages = messages;

  const res = await fetch(`${API_BASE_URL}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
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

  while (true) {
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
}

/**
 * POST /feedback — thumbs up stores (query, sql) in semantic cache; down/none logs only.
 *
 * @param {string} query
 * @param {string} response
 * @param {"up"|"down"|"none"} feedback
 * @param {{ sql?: string }} [options] — executed SQL for thumbs-up indexing (and optional log context)
 * @returns {Promise<{ status: "stored_in_vector_db" | "logged" }>}
 */
// Helper to get session ID (can be improved to use real session logic)
function getSessionId() {
  let sid = window.localStorage.getItem("session_id");
  if (!sid) {
    sid = `sess_${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem("session_id", sid);
  }
  return sid;
}

// feedback can be: "up" or "down" only
export async function submitFeedback(query, response, feedback, { sql = "" } = {}) {
  if (feedback !== "up" && feedback !== "down") {
    throw new Error("submitFeedback: feedback must be 'up' or 'down'");
  }
  const payload = {
    query,
    response,
    feedback, // "up" | "down"
    sql,
    session_id: getSessionId(),
  };
  const res = await axios.post(`${API_BASE_URL}/feedback`, payload);
  return res.data;
}

