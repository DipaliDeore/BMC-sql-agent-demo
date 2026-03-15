/**
 * Sidebar.jsx - Left Panel Component
 * ------------------------------------
 * Displays:
 *   - App title: "SQL Agent"
 *   - Dark/Light mode toggle button (top right)
 *   - "Query History" section with list of past questions
 *   - Clicking a history item re-sends that question
 *   - Empty state: "No queries yet."
 *
 * Props:
 *   theme        {string}    "dark" or "light"
 *   toggleTheme  {Function}  Toggles between dark and light mode
 *   history      {Array}     List of past question strings
 *   onSelect     {Function}  Called with the question string when a history item is clicked
 */

import React from "react";

export default function Sidebar({ theme, toggleTheme, history, onSelect }) {
  // Theme-based colors
  const isDark = theme === "dark";
  const bgColor = isDark ? "#0f0f0f" : "#ffffff";
  const textColor = isDark ? "#e5e5e5" : "#111111";
  const borderColor = isDark ? "#2a2a2a" : "#e5e5e5";
  const hoverBg = isDark ? "#1a1a1a" : "#f5f5f5";
  const mutedText = isDark ? "#888888" : "#666666";

  return (
    <aside
      style={{
        width: "25%",
        minWidth: "220px",
        backgroundColor: bgColor,
        borderRight: `1px solid ${borderColor}`,
        color: textColor,
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        overflow: "hidden",
      }}
    >
      {/* Header: App title + theme toggle */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 20px",
          borderBottom: `1px solid ${borderColor}`,
        }}
      >
        <h1 style={{ fontSize: "18px", fontWeight: 600, margin: 0 }}>
          SQL Agent
        </h1>
        <button
          id="theme-toggle-btn"
          onClick={toggleTheme}
          style={{
            padding: "6px 14px",
            fontSize: "12px",
            fontWeight: 500,
            border: `1px solid ${borderColor}`,
            borderRadius: "6px",
            backgroundColor: "transparent",
            color: textColor,
            cursor: "pointer",
          }}
        >
          {isDark ? "Light" : "Dark"}
        </button>
      </div>

      {/* Query History heading */}
      <div
        style={{
          padding: "14px 20px 8px",
          fontSize: "12px",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: mutedText,
        }}
      >
        Query History
      </div>

      {/* History list or empty state */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 12px 12px" }}>
        {history.length === 0 ? (
          <p
            style={{
              padding: "20px 8px",
              fontSize: "13px",
              color: mutedText,
              textAlign: "center",
            }}
          >
            No queries yet.
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {history.map((item, index) => (
              <li key={index}>
                <button
                  id={`history-item-${index}`}
                  onClick={() => onSelect(item)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "10px 12px",
                    fontSize: "13px",
                    lineHeight: "1.4",
                    border: "none",
                    borderRadius: "6px",
                    backgroundColor: "transparent",
                    color: textColor,
                    cursor: "pointer",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    display: "block",
                    marginBottom: "2px",
                  }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.backgroundColor = hoverBg)
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.backgroundColor = "transparent")
                  }
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
