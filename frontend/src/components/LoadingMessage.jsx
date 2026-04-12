/**
 * LoadingMessage.jsx — typing / thinking indicator
 */

import React from "react";

export default function LoadingMessage() {
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", padding: "8px 0" }}>
      <div
        style={{
          maxWidth: "min(85%, 420px)",
          padding: "14px 18px",
          borderRadius: "14px",
          borderTopLeftRadius: "4px",
          backgroundColor: "var(--assistant-bubble)",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-sm)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <span
            style={{
              display: "inline-flex",
              gap: "4px",
              alignItems: "center",
            }}
            aria-hidden
          >
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                style={{
                  width: "6px",
                  height: "6px",
                  borderRadius: "50%",
                  backgroundColor: "var(--accent)",
                  animation: "sql-agent-pulse 1.2s ease-in-out infinite",
                  animationDelay: `${i * 0.15}s`,
                }}
              />
            ))}
          </span>
          <span
            style={{
              fontSize: "14px",
              color: "var(--text-muted)",
              fontWeight: 500,
            }}
          >
            Thinking…
          </span>
        </div>
      </div>
    </div>
  );
}
