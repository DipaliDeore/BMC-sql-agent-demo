/**
 * ChatWindow.jsx - Main Chat Area Component (Right Panel)
 * --------------------------------------------------------
 * Displays:
 *   - Fixed header with title "AI Data Assistant"
 *   - Scrollable chat message area
 *   - Fixed input bar with text input and "Run" button
 *
 * Props:
 *   theme       {string}    "dark" or "light"
 *   messages    {Array}     Array of message objects
 *   loading     {boolean}   Whether a request is in progress
 *   onSend      {Function}  Called with the question string when user submits
 *   inputValue  {string}    Current value of the input field
 *   setInputValue {Function} Setter for the input field value
 */

import React, { useRef, useEffect } from "react";
import MessageBubble from "./MessageBubble";
import LoadingMessage from "./LoadingMessage";

export default function ChatWindow({ theme, messages, loading, onSend, inputValue, setInputValue }) {
  const isDark = theme === "dark";
  const bottomRef = useRef(null);

  // Theme colors
  const bgColor = isDark ? "#0f0f0f" : "#ffffff";
  const headerBg = isDark ? "#0f0f0f" : "#ffffff";
  const borderColor = isDark ? "#2a2a2a" : "#e5e5e5";
  const textColor = isDark ? "#e5e5e5" : "#111111";
  const mutedText = isDark ? "#888888" : "#666666";
  const inputBg = isDark ? "#1a1a1a" : "#f5f5f5";

  // Auto-scroll to the bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Handle form submission
  function handleSubmit(e) {
    e.preventDefault();
    const question = inputValue.trim();
    if (!question || loading) return;
    onSend(question);
    setInputValue("");
  }

  // Handle Enter key press (submit on Enter, newline on Shift+Enter)
  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      handleSubmit(e);
    }
  }

  return (
    <div
      style={{
        width: "75%",
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        backgroundColor: bgColor,
      }}
    >
      {/* Fixed Header */}
      <div
        style={{
          padding: "16px 24px",
          borderBottom: `1px solid ${borderColor}`,
          backgroundColor: headerBg,
          flexShrink: 0,
        }}
      >
        <h2
          style={{
            fontSize: "16px",
            fontWeight: 600,
            color: textColor,
            margin: 0,
          }}
        >
          AI Data Assistant
        </h2>
      </div>

      {/* Scrollable Message Area */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "20px 24px",
        }}
      >
        {/* Empty state */}
        {messages.length === 0 && !loading && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              color: mutedText,
              fontSize: "14px",
            }}
          >
            Ask a question about your database to get started.
          </div>
        )}

        {/* Render each message */}
        {messages.map((msg, index) => (
          <MessageBubble key={index} message={msg} theme={theme} />
        ))}

        {/* Loading state */}
        {loading && <LoadingMessage theme={theme} />}

        {/* Scroll anchor */}
        <div ref={bottomRef} />
      </div>

      {/* Fixed Input Bar */}
      <div
        style={{
          padding: "16px 24px",
          borderTop: `1px solid ${borderColor}`,
          backgroundColor: headerBg,
          flexShrink: 0,
        }}
      >
        <form
          onSubmit={handleSubmit}
          style={{ display: "flex", gap: "12px", alignItems: "center" }}
        >
          <input
            id="chat-input"
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your data..."
            disabled={loading}
            style={{
              flex: 1,
              padding: "12px 16px",
              fontSize: "14px",
              borderRadius: "8px",
              border: `1px solid ${borderColor}`,
              backgroundColor: inputBg,
              color: textColor,
              outline: "none",
              fontFamily: "Inter, sans-serif",
              opacity: loading ? 0.5 : 1,
            }}
          />
          <button
            id="run-button"
            type="submit"
            disabled={loading || !inputValue.trim()}
            style={{
              padding: "12px 24px",
              fontSize: "14px",
              fontWeight: 600,
              borderRadius: "8px",
              border: "none",
              backgroundColor: loading || !inputValue.trim() ? "#666666" : "#333333",
              color: "#ffffff",
              cursor: loading || !inputValue.trim() ? "not-allowed" : "pointer",
              fontFamily: "Inter, sans-serif",
              opacity: loading || !inputValue.trim() ? 0.5 : 1,
            }}
          >
            Run
          </button>
        </form>
      </div>
    </div>
  );
}
