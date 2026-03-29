/**
 * Sidebar.jsx - Left Panel Component
 */

import React from "react";

export default function Sidebar({ theme, toggleTheme, history, onSelect }) {
  const isDark = theme === "dark";

  return (
    <aside
      className="app-sidebar"
      style={{
        width: "clamp(220px, 26%, 300px)",
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
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          padding: "18px 20px",
          borderBottom: "1px solid var(--border-subtle)",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              height: "3px",
              width: "40px",
              borderRadius: "2px",
              background: "var(--header-accent)",
              marginBottom: "10px",
            }}
          />
          <h1
            style={{
              fontSize: "17px",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              margin: 0,
              lineHeight: 1.2,
            }}
          >
            SQL Agent
          </h1>
        </div>
        <button
          id="theme-toggle-btn"
          type="button"
          onClick={toggleTheme}
          aria-pressed={isDark}
          aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
          style={{
            flexShrink: 0,
            padding: "8px 14px",
            fontSize: "12px",
            fontWeight: 600,
            border: "1px solid var(--border)",
            borderRadius: "999px",
            backgroundColor: "var(--surface-2)",
            color: "var(--text)",
            cursor: "pointer",
            transition: "background-color 0.15s ease, border-color 0.15s ease",
          }}
        >
          {isDark ? "Light" : "Dark"}
        </button>
      </div>

      <div
        style={{
          padding: "14px 20px 8px",
          fontSize: "11px",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          color: "var(--text-muted)",
        }}
      >
        Query history
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "4px 12px 16px" }}>
        {history.length === 0 ? (
          <p
            style={{
              padding: "24px 12px",
              fontSize: "13px",
              color: "var(--text-muted)",
              textAlign: "center",
              lineHeight: 1.5,
            }}
          >
            Your questions will appear here so you can rerun them quickly.
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {history.map((item, index) => (
              <li key={`${item}-${index}`}>
                <button
                  id={`history-item-${index}`}
                  type="button"
                  title={item}
                  onClick={() => onSelect(item)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "11px 14px",
                    fontSize: "13px",
                    lineHeight: 1.45,
                    border: "1px solid transparent",
                    borderRadius: "10px",
                    backgroundColor: "transparent",
                    color: "var(--text)",
                    cursor: "pointer",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    display: "block",
                    marginBottom: "4px",
                    transition: "background-color 0.12s ease, border-color 0.12s ease",
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = "var(--surface-2)";
                    e.currentTarget.style.borderColor = "var(--border-subtle)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = "transparent";
                    e.currentTarget.style.borderColor = "transparent";
                  }}
                >
                  {item}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
