/**
 * Sidebar.jsx — New chat + recent chats (ChatGPT-style)
 */

import React, { useEffect, useState } from "react";

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

const menuSurface = {
  backgroundColor: "var(--surface-1)",
  border: "1px solid var(--border)",
  borderRadius: "8px",
  boxShadow: "0 8px 24px rgba(0,0,0,0.18)",
  minWidth: "140px",
  padding: "4px 0",
  zIndex: 30,
};

const menuItem = {
  display: "block",
  width: "100%",
  padding: "8px 14px",
  fontSize: "13px",
  textAlign: "left",
  border: "none",
  background: "transparent",
  color: "var(--text)",
  cursor: "pointer",
};

export default function Sidebar({
  chats,
  activeChatId,
  onNewChat,
  onSelectChat,
  onRenameChat,
  onDeleteChat,
}) {
  const [hoveredRowId, setHoveredRowId] = useState(null);
  const [menuOpenId, setMenuOpenId] = useState(null);

  useEffect(() => {
    if (menuOpenId == null) return;
    const onDocMouseDown = (e) => {
      const root = e.target.closest?.("[data-chat-menu-root]");
      if (root && root.getAttribute("data-chat-menu-root") === menuOpenId) return;
      setMenuOpenId(null);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [menuOpenId]);

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
      <div style={{ padding: "18px 14px 10px" }}>
        <button type="button" className="sidebar-new-chat" onClick={onNewChat}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14M5 12h14"/></svg>
          New chat
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "0 12px" }}>
        <div style={{ marginTop: "20px", marginBottom: "14px" }}>
          <div
            style={{
              padding: "0 12px 10px",
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--text-muted)",
            }}
          >
            Recents
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {chats.map((c) => {
              const active = c.id === activeChatId;
              const showActions = hoveredRowId === c.id || menuOpenId === c.id;
              const menuOpen = menuOpenId === c.id;
              const title = c.title || "New chat";

              return (
                <div
                  key={c.id}
                  data-chat-menu-root={c.id}
                  title={formatChatTime(c.updated_at) || undefined}
                  onMouseEnter={() => setHoveredRowId(c.id)}
                  onMouseLeave={() => setHoveredRowId((id) => (id === c.id ? null : id))}
                  style={{
                    position: "relative",
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    padding: "4px 6px 4px 8px",
                    borderRadius: "8px",
                    backgroundColor:
                      active || hoveredRowId === c.id || menuOpenId === c.id
                        ? "var(--surface-1)"
                        : "transparent",
                    transition: "background-color 0.15s ease, color 0.15s ease",
                  }}
                >
                  <button
                    type="button"
                    onClick={() => onSelectChat(c.id)}
                    style={{
                      flex: 1,
                      minWidth: 0,
                      padding: "6px 4px 6px 6px",
                      fontSize: "13.5px",
                      border: "none",
                      borderRadius: "6px",
                      background: "transparent",
                      color: active ? "var(--text)" : "var(--text-muted)",
                      cursor: "pointer",
                      textAlign: "left",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                    onMouseOver={(e) => {
                      if (!active) {
                        e.currentTarget.style.color = "var(--text)";
                      }
                    }}
                    onMouseOut={(e) => {
                      if (!active) {
                        e.currentTarget.style.color = "var(--text-muted)";
                      }
                    }}
                  >
                    {title}
                  </button>

                  {showActions && (
                    <button
                      type="button"
                      aria-label="Chat options"
                      aria-expanded={menuOpen}
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(menuOpen ? null : c.id);
                      }}
                      style={{
                        flexShrink: 0,
                        width: "28px",
                        height: "28px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        border: "none",
                        borderRadius: "6px",
                        backgroundColor: menuOpen ? "var(--surface-1)" : "transparent",
                        color: "var(--text-muted)",
                        cursor: "pointer",
                      }}
                      onMouseOver={(e) => {
                        e.currentTarget.style.backgroundColor = "var(--surface-1)";
                        e.currentTarget.style.color = "var(--text)";
                      }}
                      onMouseOut={(e) => {
                        if (!menuOpen) e.currentTarget.style.backgroundColor = "transparent";
                        e.currentTarget.style.color = menuOpen ? "var(--text)" : "var(--text-muted)";
                      }}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                        <circle cx="5" cy="12" r="2" />
                        <circle cx="12" cy="12" r="2" />
                        <circle cx="19" cy="12" r="2" />
                      </svg>
                    </button>
                  )}

                  {menuOpen && (
                    <div
                      role="menu"
                      style={{
                        position: "absolute",
                        right: "4px",
                        top: "calc(100% - 2px)",
                        ...menuSurface,
                      }}
                      onMouseDown={(e) => e.stopPropagation()}
                    >
                      <button
                        type="button"
                        role="menuitem"
                        style={menuItem}
                        onMouseOver={(e) => {
                          e.currentTarget.style.backgroundColor = "var(--sidebar-bg)";
                        }}
                        onMouseOut={(e) => {
                          e.currentTarget.style.backgroundColor = "transparent";
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpenId(null);
                          onRenameChat(c.id, title);
                        }}
                      >
                        Rename
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        style={{ ...menuItem, color: "var(--error)" }}
                        onMouseOver={(e) => {
                          e.currentTarget.style.backgroundColor = "var(--sidebar-bg)";
                        }}
                        onMouseOut={(e) => {
                          e.currentTarget.style.backgroundColor = "transparent";
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setMenuOpenId(null);
                          onDeleteChat(c.id);
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </aside>
  );
}
