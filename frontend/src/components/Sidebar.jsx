/**
 * Sidebar.jsx — New chat + recent chats (ChatGPT-style)
 */

import React from "react";

function formatChatTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

export default function Sidebar({
  chats,
  activeChatId,
  onNewChat,
  onSelectChat,
  onRenameChat,
  onDeleteChat,
}) {
  return (
    <aside
      className="app-sidebar"
      style={{
        width: "260px",
        flexShrink: 0,
        backgroundColor: "var(--sidebar-bg)",
        borderRight: "1px solid var(--border)",
        color: "var(--text)",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
      }}
    >
      {/* Top Section: New Chat */}
      <div style={{ padding: "16px 12px 8px" }}>
        <button
          type="button"
          onClick={onNewChat}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: "10px",
            padding: "10px 12px",
            fontSize: "14px",
            fontWeight: 500,
            borderRadius: "8px",
            border: "none",
            backgroundColor: "transparent",
            color: "var(--text)",
            cursor: "pointer",
            textAlign: "left",
            transition: "background-color 0.15s ease",
          }}
          onMouseOver={(e) => (e.currentTarget.style.backgroundColor = "var(--surface-1)")}
          onMouseOut={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
          New chat
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "0 12px" }}>
        {/* Recents Section */}
        <div style={{ marginTop: "24px", marginBottom: "16px" }}>
          <div style={{ padding: "0 12px 8px", fontSize: "12px", fontWeight: 600, color: "var(--text-muted)" }}>
            Recents
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {chats.map((c) => {
              const active = c.id === activeChatId;
              return (
                <div
                  key={c.id}
                  onClick={() => onSelectChat(c.id)}
                  style={{
                    padding: "8px 12px",
                    fontSize: "13.5px",
                    borderRadius: "8px",
                    backgroundColor: active ? "var(--surface-1)" : "transparent",
                    color: active ? "var(--text)" : "var(--text-muted)",
                    cursor: "pointer",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    transition: "background-color 0.15s ease, color 0.15s ease",
                  }}
                  onMouseOver={(e) => {
                    if (!active) e.currentTarget.style.backgroundColor = "var(--surface-1)";
                    if (!active) e.currentTarget.style.color = "var(--text)";
                  }}
                  onMouseOut={(e) => {
                    if (!active) e.currentTarget.style.backgroundColor = "transparent";
                    if (!active) e.currentTarget.style.color = "var(--text-muted)";
                  }}
                >
                  {c.title || "New chat"}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
}
