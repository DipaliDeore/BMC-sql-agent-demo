/**
 * ChatWindow.jsx - Main Chat Area Component (Right Panel)
 */

import React, { useRef, useEffect, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import LoadingMessage from "./LoadingMessage";

export default function ChatWindow({ theme, messages, loading, onSend, inputValue, setInputValue }) {
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);

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
    e.preventDefault();
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
      }}
    >
      <header
        style={{
          padding: "18px 28px",
          borderBottom: "1px solid var(--border-subtle)",
          backgroundColor: "var(--surface-1)",
          flexShrink: 0,
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <h2
          style={{
            fontSize: "17px",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            color: "var(--text)",
            margin: 0,
          }}
        >
          AI Data Assistant
        </h2>
      </header>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "24px 28px",
          minHeight: 0,
        }}
      >
        {messages.length === 0 && !loading && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              minHeight: "min(320px, 50vh)",
              textAlign: "center",
              padding: "24px 16px",
            }}
          >
            <div
              style={{
                width: "56px",
                height: "56px",
                borderRadius: "16px",
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: "20px",
                fontSize: "26px",
              }}
              aria-hidden
            >
              ✦
            </div>
            <p
              style={{
                color: "var(--text)",
                fontSize: "16px",
                fontWeight: 600,
                marginBottom: "8px",
                maxWidth: "360px",
              }}
            >
              Explore your data with questions
            </p>
            <p
              style={{
                color: "var(--text-muted)",
                fontSize: "14px",
                lineHeight: 1.55,
                maxWidth: "400px",
                marginBottom: 0,
              }}
            >
              Describe what you want to know. The assistant finds the relevant data and summarizes the results.
            </p>
          </div>
        )}

        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {messages.map((msg, index) => (
            <MessageBubble
              key={msg.role === "user" ? `u-${index}-${msg.content}` : `a-${index}`}
              message={msg}
              theme={theme}
              onSend={onSend}
            />
          ))}
        </div>

        {loading && <LoadingMessage />}

        <div ref={bottomRef} style={{ height: "1px" }} />
      </div>

      <div
        style={{
          padding: "16px 28px 20px",
          borderTop: "1px solid var(--border-subtle)",
          backgroundColor: "var(--surface-1)",
          flexShrink: 0,
        }}
      >
        <form
          onSubmit={handleSubmit}
          style={{
            display: "flex",
            gap: "12px",
            alignItems: "flex-end",
            maxWidth: "900px",
            margin: "0 auto",
          }}
        >
          <textarea
            ref={textareaRef}
            id="chat-input"
            rows={1}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your data…"
            disabled={loading}
            aria-label="Question for the data assistant"
            style={{
              flex: 1,
              minHeight: "48px",
              maxHeight: "160px",
              padding: "13px 16px",
              fontSize: "14px",
              lineHeight: 1.45,
              borderRadius: "12px",
              border: "1px solid var(--border)",
              backgroundColor: "var(--surface-2)",
              color: "var(--text)",
              resize: "none",
              fontFamily: "inherit",
              opacity: loading ? 0.65 : 1,
              boxShadow: "inset 0 1px 2px rgba(0,0,0,0.04)",
            }}
          />
          <button
            id="run-button"
            type="submit"
            disabled={loading || !inputValue.trim()}
            style={{
              flexShrink: 0,
              padding: "13px 22px",
              minHeight: "48px",
              fontSize: "14px",
              fontWeight: 600,
              borderRadius: "12px",
              border: "none",
              backgroundColor:
                loading || !inputValue.trim() ? "var(--surface-3)" : "var(--accent)",
              color: loading || !inputValue.trim() ? "var(--text-muted)" : "var(--accent-fg)",
              cursor: loading || !inputValue.trim() ? "not-allowed" : "pointer",
              fontFamily: "inherit",
              boxShadow:
                loading || !inputValue.trim()
                  ? "none"
                  : "0 2px 8px rgba(79, 70, 229, 0.35)",
              transition: "background-color 0.15s ease, transform 0.1s ease",
            }}
            onMouseDown={(e) => {
              if (!loading && inputValue.trim()) e.currentTarget.style.transform = "scale(0.98)";
            }}
            onMouseUp={(e) => {
              e.currentTarget.style.transform = "";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = "";
            }}
          >
            Run
          </button>
        </form>
        <p
          style={{
            fontSize: "11px",
            color: "var(--text-muted)",
            marginTop: "10px",
            textAlign: "center",
            maxWidth: "900px",
            marginLeft: "auto",
            marginRight: "auto",
          }}
        >
          Enter to send · Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
}
