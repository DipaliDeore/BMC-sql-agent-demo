/**
 * agent.js - API Layer
 * --------------------
 * Handles all API communication with the FastAPI backend.
 * Uses axios to send POST requests to the /api/query endpoint.
 */

import axios from "axios";

// Backend base URL
const API_BASE_URL = "http://localhost:8000";

const DEFAULT_ERROR_MESSAGE =
  "Hmm, something went wrong. Could you try again in a moment?";

/**
 * Human-friendly message from an axios/API error (FastAPI often returns { detail: string }).
 */
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
 * Send a natural language question to the backend.
 *
 * @param {string} question - The user's question in plain English
 * @returns {Promise<Object>} - Response with: question, sql, results, explanation, row_count
 * @throws {Error} - If the API request fails
 */
/**
 * @param {string} question
 * @param {string} [conversationId] - Stable per-session id for multi-turn memory (MemorySaver thread)
 */
export async function sendQuery(question, conversationId) {
  const body = { question };
  if (conversationId) body.conversation_id = conversationId;
  const response = await axios.post(`${API_BASE_URL}/api/query`, body);
  return response.data;
}
