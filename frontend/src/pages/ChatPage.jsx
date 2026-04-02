/**
 * ChatPage.jsx - Main Page Component
 * ------------------------------------
 * Composes the Sidebar and ChatWindow components.
 * Manages all application state:
 *   - messages: array of chat messages
 *   - history: array of past question strings
 *   - loading: whether a request is in progress
 *   - inputValue: current input field value
 *
 * Handles:
 *   - Sending questions to the API via agent.js
 *   - Adding messages and history entries
 *   - Error handling
 *   - Re-sending questions from history
 *
 * Props:
 *   theme        {string}    "dark" or "light"
 *   toggleTheme  {Function}  Toggles between dark and light mode
 */

import React, { useRef, useState } from "react";
import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";
import { sendQuery, getApiErrorMessage } from "../api/agent";

export default function ChatPage({ theme, toggleTheme }) {
  // State: chat messages, query history, loading indicator, input value
  const [messages, setMessages] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const conversationIdRef = useRef(
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );

  /**
   * Handle sending a question to the backend.
   * Called when user clicks "Run" or presses Enter.
   */
  async function handleSend(question) {
    // Add the user message to the chat
    const userMessage = {
      role: "user",
      content: question,
    };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    try {
      // Call the backend API
      const data = await sendQuery(question, conversationIdRef.current, "AUTO");
      if (data.conversation_id) conversationIdRef.current = data.conversation_id;

      // Create the assistant response message
      const assistantMessage = {
        role: "assistant",
        sql: data.sql,
        results: data.results,
        explanation: data.explanation,
        row_count: data.row_count,
        result_sentence: data.result_sentence ?? null,
        cache_references: data.cache_references ?? null,
        is_multi: data.is_multi ?? false,
        sub_responses: data.sub_responses ?? [],
        is_ambiguous: data.is_ambiguous ?? false,
        original_question: question,
      };

      // Add assistant message to the chat
      setMessages((prev) => [...prev, assistantMessage]);

      // Add question to history (newest first)
      setHistory((prev) => [question, ...prev]);
    } catch (error) {
      const errorMessage = {
        role: "assistant",
        error: true,
        errorText: getApiErrorMessage(error),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  }

  /**
   * Handle clicking a query history item.
   * Re-sends the selected question.
   */
  function handleHistorySelect(question) {
    setInputValue(question);
    handleSend(question);
  }

  return (
    <div className="app-shell">
      <Sidebar
        theme={theme}
        toggleTheme={toggleTheme}
        history={history}
        onSelect={handleHistorySelect}
      />

      <ChatWindow
        theme={theme}
        messages={messages}
        loading={loading}
        onSend={handleSend}
        inputValue={inputValue}
        setInputValue={setInputValue}
      />
    </div>
  );
}
