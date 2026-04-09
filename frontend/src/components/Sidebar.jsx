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
        width: "clamp(240px, 28%, 300px)",
        flexShrink: 0,
        backgroundColor: "var(--surface-1)",
        borderRight: "1px solid var(--border)",
        color: "var(--text)",
        display: "flex",
        flexDirection: "column",
        height: "100%",
        overflow: "hidden",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <div
        style={{
          padding: "16px 14px 12px",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <div
          style={{
            height: "3px",
            width: "36px",
            borderRadius: "2px",
            background: "var(--header-accent)",
            marginBottom: "10px",
          }}
        />
        <h1
          style={{
            fontSize: "16px",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            margin: "0 0 14px",
            lineHeight: 1.2,
          }}
        >
          SQL Agent
        </h1>
        <button
          type="button"
          onClick={onNewChat}
          style={{
            width: "100%",
            padding: "11px 14px",
            fontSize: "14px",
            fontWeight: 600,
            borderRadius: "10px",
            border: "1px solid var(--border)",
            backgroundColor: "var(--surface-2)",
            color: "var(--text)",
            cursor: "pointer",
            fontFamily: "inherit",
            transition: "background-color 0.15s ease",
          }}
        >
          + New chat
        </button>
      </div>

      <div
        style={{
          padding: "10px 14px 6px",
          fontSize: "11px",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--text-muted)",
        }}
      >
        Recent chats
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "4px 10px 16px" }}>
        {chats.length === 0 ? (
          <p
            style={{
              padding: "20px 10px",
              fontSize: "13px",
              color: "var(--text-muted)",
              textAlign: "center",
              lineHeight: 1.5,
            }}
          >
            No chats yet. Start with <strong>New chat</strong>.
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {chats.map((c) => {
              const active = c.id === activeChatId;
              return (
                <li key={c.id} style={{ marginBottom: "6px" }}>
                  <div
                    style={{
                      borderRadius: "10px",
                      border: active ? "1px solid var(--accent)" : "1px solid transparent",
                      backgroundColor: active ? "var(--surface-2)" : "transparent",
                      padding: "8px 10px",
                      transition: "background-color 0.12s ease, border-color 0.12s ease",
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectChat(c.id)}
                      title={c.title}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        padding: "4px 0",
                        fontSize: "13px",
                        fontWeight: active ? 600 : 500,
                        lineHeight: 1.4,
                        border: "none",
                        background: "transparent",
                        color: "var(--text)",
                        cursor: "pointer",
                        display: "block",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        fontFamily: "inherit",
                      }}
                    >
                      {c.title || "New chat"}
                    </button>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: "8px",
                        marginTop: "4px",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "11px",
                          color: "var(--text-muted)",
                        }}
                      >
                        {formatChatTime(c.updated_at)}
                      </span>
                      <span style={{ display: "flex", gap: "6px", flexShrink: 0 }}>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRenameChat(c.id, c.title);
                          }}
                          style={{
                            fontSize: "11px",
                            padding: "2px 6px",
                            border: "none",
                            background: "transparent",
                            color: "var(--text-muted)",
                            cursor: "pointer",
                            fontFamily: "inherit",
                          }}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteChat(c.id);
                          }}
                          style={{
                            fontSize: "11px",
                            padding: "2px 6px",
                            border: "none",
                            background: "transparent",
                            color: "var(--error)",
                            cursor: "pointer",
                            fontFamily: "inherit",
                          }}
                        >
                          Delete
                        </button>
                      </span>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
