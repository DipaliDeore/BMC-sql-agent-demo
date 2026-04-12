/**
 * ChatWindow.jsx — scrollable messages + fixed input; theme toggle top-right
 */

import React, { useRef, useEffect, useCallback } from "react";
import MessageBubble from "./MessageBubble";
import LoadingMessage from "./LoadingMessage";

export default function ChatWindow({
  theme,
  toggleTheme,
  chatTitle,
  conversationId,
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
      <header
        style={{
          padding: "12px 20px",
          backgroundColor: "var(--app-bg)",
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          zIndex: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text)" }}>AI SQL Agent</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="m6 9 6 6 6-6"/></svg>
        </div>
        
        <div style={{ display: "flex", gap: "10px" }}>
           <button
             type="button"
             onClick={toggleTheme}
             style={{
               width: "32px",
               height: "32px",
               borderRadius: "50%",
               border: "1px solid var(--border)",
               backgroundColor: "transparent",
               color: "var(--text)",
               cursor: "pointer",
               display: "flex",
               alignItems: "center",
               justifyContent: "center",
               fontSize: "14px"
             }}
           >
             {isDark ? "🔆" : "🌙"}
           </button>
        </div>
      </header>

      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "0 0 100px",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        <div style={{ width: "100%", maxWidth: "800px", padding: "0 24px" }}>
          {messages.length === 0 && !loading && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                minHeight: "min(320px, 60vh)",
                textAlign: "center",
              }}
            >
              <h1
                style={{
                  color: "var(--text)",
                  fontSize: "28px",
                  fontWeight: 600,
                  marginBottom: "40px",
                }}
              >
                Hello! How can I help you find insights today?
              </h1>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: "24px", paddingTop: "20px" }}>
            {messages.map((msg, index) => (
              <MessageBubble
                key={msg.id != null ? String(msg.id) : `m-${index}`}
                message={msg}
                theme={theme}
                conversationId={conversationId}
                onSend={onSend}
              />
            ))}
          </div>

          {loading && <LoadingMessage />}
        </div>
        <div ref={bottomRef} style={{ height: "40px" }} />
      </div>

      {/* Pill-shaped Floating Input */}
      <div
        style={{
          position: "absolute",
          bottom: "24px",
          left: "50%",
          transform: "translateX(-50%)",
          width: "calc(100% - 48px)",
          maxWidth: "768px",
          zIndex: 20,
        }}
      >
        <form
          onSubmit={handleSubmit}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            padding: "8px 12px 8px 16px",
            backgroundColor: "var(--surface-1)",
            border: "1px solid var(--border)",
            borderRadius: "26px",
            boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
          }}
        >
          <button type="button" style={{ background: "transparent", border: "none", color: "var(--text-muted)", cursor: "pointer" }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>
          </button>
          
          <textarea
            ref={textareaRef}
            rows={1}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything"
            disabled={loading}
            style={{
              flex: 1,
              backgroundColor: "transparent",
              border: "none",
              color: "var(--text)",
              fontSize: "15px",
              padding: "4px 0",
              resize: "none",
              fontFamily: "inherit",
              outline: "none",
              maxHeight: "200px",
              lineHeight: "1.5"
            }}
          />

          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <button 
              type="submit" 
              disabled={loading || !inputValue.trim()}
              style={{ 
                width: "32px", 
                height: "32px", 
                borderRadius: "50%", 
                backgroundColor: loading || !inputValue.trim() ? "var(--surface-3)" : "var(--text)", 
                color: loading || !inputValue.trim() ? "var(--text-muted)" : "var(--app-bg)", 
                border: "none", 
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center"
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 7-7 7 7M12 19V5"/></svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
