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

const MAX_ATTACH = 4;
const MAX_IMAGE_BYTES = 4 * 1024 * 1024;

function readImageFile(file) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error("not_image"));
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      reject(new Error("too_large"));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      if (typeof dataUrl !== "string") {
        reject(new Error("read_fail"));
        return;
      }
      const m = /^data:([^;]+);base64,(.+)$/.exec(dataUrl);
      if (!m) {
        reject(new Error("parse_fail"));
        return;
      }
      resolve({
        id: `att-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
        preview: dataUrl,
        media_type: m[1] || "image/png",
        data_base64: m[2],
      });
    };
    reader.onerror = () => reject(new Error("read_fail"));
    reader.readAsDataURL(file);
  });
}

export default function ChatWindow({
  theme,
  toggleTheme,
  messages,
  loading,
  onSend,
  onStop,
  onRetry,
  inputValue,
  setInputValue,
  pendingImages = [],
  onPendingImagesChange,
}) {
  const bottomRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const isDark = theme === "dark";
  const hasStreamingAssistant = messages.some((m) => m.streaming);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const resizeTextarea = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    resizeTextarea();
  }, [inputValue, resizeTextarea]);

  function handleSubmit(e) {
    if (e) e.preventDefault();
    const question = inputValue.trim();
    if ((!question && !pendingImages.length) || loading) return;
    onSend(question);
    setInputValue("");
    requestAnimationFrame(resizeTextarea);
  }

  async function handleFilePick(e) {
    const files = e.target.files;
    if (!files?.length || !onPendingImagesChange) return;
    const room = MAX_ATTACH - pendingImages.length;
    if (room <= 0) return;
    const picked = Array.from(files).slice(0, room);
    const next = [...pendingImages];
    for (const f of picked) {
      try {
        next.push(await readImageFile(f));
      } catch {
        /* skip invalid */
      }
    }
    onPendingImagesChange(next);
    e.target.value = "";
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
                onRetry={onRetry}
              />
            ))}
          </div>

          {loading && !hasStreamingAssistant && <LoadingMessage />}
        </div>
        <div ref={bottomRef} style={{ height: "32px" }} />
      </div>

      <div className="chat-composer-wrap">
        <form className="chat-composer" onSubmit={handleSubmit}>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            style={{ display: "none" }}
            onChange={handleFilePick}
          />
          {pendingImages.length > 0 && onPendingImagesChange ? (
            <div className="chat-composer-attachments" aria-label="Attached images">
              {pendingImages.map((im) => (
                <div key={im.id} className="chat-composer-attachment-slot">
                  <img
                    src={im.preview}
                    alt=""
                    className="chat-composer-attachment-thumb"
                  />
                  <button
                    type="button"
                    className="chat-composer-attachment-remove"
                    aria-label="Remove attachment"
                    disabled={loading}
                    onClick={() =>
                      onPendingImagesChange(pendingImages.filter((x) => x.id !== im.id))
                    }
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          <div className="chat-composer-row">
            <button
              type="button"
              className="icon-btn-ghost chat-composer-attach-btn"
              disabled={loading}
              aria-label="Attach image"
              onClick={() => fileInputRef.current?.click()}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="M21 15l-5-5L5 21" />
              </svg>
            </button>
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

            {loading ? (
              <button
                type="button"
                className="chat-stop-btn"
                onClick={() => onStop?.()}
                aria-label="Stop generating"
              >
                Stop
              </button>
            ) : (
              <button
                type="submit"
                className="chat-send-btn"
                disabled={!inputValue.trim() && !pendingImages.length}
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
            )}
          </div>
        </form>
      </div>
    </div>
  );
}
