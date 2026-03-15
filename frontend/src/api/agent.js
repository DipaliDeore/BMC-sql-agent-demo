/**
 * agent.js - API Layer
 * --------------------
 * Handles all API communication with the FastAPI backend.
 * Uses axios to send POST requests to the /api/query endpoint.
 */

import axios from "axios";

// Backend base URL
const API_BASE_URL = "http://localhost:8000";

/**
 * Send a natural language question to the backend.
 *
 * @param {string} question - The user's question in plain English
 * @returns {Promise<Object>} - Response with: question, sql, results, explanation, row_count
 * @throws {Error} - If the API request fails
 */
export async function sendQuery(question) {
  const response = await axios.post(`${API_BASE_URL}/api/query`, {
    question: question,
  });
  return response.data;
}
