/**
 * LoadingMessage.jsx — typing / thinking indicator
 */

import React from "react";

export default function LoadingMessage() {
  return (
    <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-start", padding: "4px 0" }}>
      <div className="loading-msg-card">
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span
            style={{
              display: "inline-flex",
              gap: "5px",
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
                  animation: "sql-agent-pulse 1.15s ease-in-out infinite",
                  animationDelay: `${i * 0.14}s`,
                }}
              />
            ))}
          </span>
          <span
            style={{
              fontSize: "14px",
              color: "var(--text-muted)",
              fontWeight: 500,
              letterSpacing: "0.01em",
            }}
          >
            Thinking…
          </span>
        </div>
      </div>
    </div>
  );
}
