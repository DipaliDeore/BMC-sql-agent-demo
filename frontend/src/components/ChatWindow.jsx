/**
 * ChatWindow.jsx — scrollable messages + fixed input; theme toggle top-right
 */

import React, { useRef, useEffect, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import LoadingMessage from "./LoadingMessage";

/** Last user message text before this index (for feedback pairing). */
function pairedUserQueryForIndex(messages, index) {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages[i]?.role === "user") return (messages[i].content || "").trim();
  }
  return "";
}

export default function ChatWindow({
  theme,
  toggleTheme,
  messages,
  loading,
  onSend,
  inputValue,
  setInputValue,
}) {
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const isDark = theme === "dark";

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [inputValue, resizeTextarea]);

  function handleSubmit(e) {
    if (e) e.preventDefault();
    const question = inputValue.trim();
    if (!question || loading) return;
    onSend(question);
    setInputValue("");
    requestAnimationFrame(resizeTextarea);
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <div
      className="app-chat"
      style={{
        flex: "1 1 0",
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        height: "100%",
        backgroundColor: "var(--app-bg)",
        position: "relative",
      }}
    >
      <header className="chat-header-bar">
        <div style={{ minWidth: 0 }}>
          <div className="chat-header-brand">SQL Agent</div>
        </div>

        <button
          type="button"
          className="icon-btn-ghost"
          onClick={toggleTheme}
          aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
        >
          {isDark ? "🔆" : "🌙"}
        </button>
      </header>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "0 0 108px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        <div style={{ width: "100%", maxWidth: "820px", padding: "0 clamp(16px, 4vw, 28px)" }}>
          {messages.length === 0 && !loading && (
            <div className="chat-empty-state">
              <h1>Hello! How can I help you find insights today?</h1>
              <p>Ask in plain language — I’ll translate to SQL and explain the results.</p>
            </div>
          )}

          <div className="chat-messages-stack">
            {messages.map((msg, index) => (
              <MessageBubble
                key={msg.id != null ? String(msg.id) : `m-${index}`}
                message={msg}
                theme={theme}
                pairedUserQuery={pairedUserQueryForIndex(messages, index)}
              />
            ))}
          </div>

          {loading && <LoadingMessage />}
        </div>
        <div ref={bottomRef} style={{ height: "32px" }} />
      </div>

      <div className="chat-composer-wrap">
        <form className="chat-composer" onSubmit={handleSubmit}>
          <textarea
            ref={textareaRef}
            rows={1}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question…"
            disabled={loading}
            aria-label="Message"
          />

          <button
            type="submit"
            className="chat-send-btn"
            disabled={loading || !inputValue.trim()}
            aria-label="Send message"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              <path d="m5 12 7-7 7 7M12 19V5" />
            </svg>
          </button>
        </form>
      </div>
    </div>
  );
}
