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

import React, { useState } from "react";
import Sidebar from "../components/Sidebar";
import ChatWindow from "../components/ChatWindow";
import { sendQuery } from "../api/agent";

export default function ChatPage({ theme, toggleTheme }) {
  // State: chat messages, query history, loading indicator, input value
  const [messages, setMessages] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");

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
      const data = await sendQuery(question);

      // Create the assistant response message
      const assistantMessage = {
        role: "assistant",
        sql: data.sql,
        results: data.results,
        explanation: data.explanation,
        row_count: data.row_count,
      };

      // Add assistant message to the chat
      setMessages((prev) => [...prev, assistantMessage]);

      // Add question to history (newest first)
      setHistory((prev) => [question, ...prev]);
    } catch (error) {
      // Add error message to the chat
      const errorMessage = {
        role: "assistant",
        error: true,
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
    <div style={{ display: "flex", height: "100vh", overflow: "hidden" }}>
      {/* Left Panel: Sidebar (25% width) */}
      <Sidebar
        theme={theme}
        toggleTheme={toggleTheme}
        history={history}
        onSelect={handleHistorySelect}
      />

      {/* Right Panel: Chat Window (75% width) */}
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
