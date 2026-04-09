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
