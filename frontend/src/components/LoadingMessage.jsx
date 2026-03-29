/**
 * LoadingMessage.jsx - Sequential loading status
 */

import React, { useState, useEffect } from "react";

const LOADING_MESSAGES = [
  "Taking a look at your question…",
  "Working out the right query…",
  "Grabbing your results…",
];

export default function LoadingMessage() {
  const [visibleCount, setVisibleCount] = useState(1);

  useEffect(() => {
    if (visibleCount < LOADING_MESSAGES.length) {
      const timer = setTimeout(() => {
        setVisibleCount((prev) => prev + 1);
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [visibleCount]);

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", padding: "8px 0" }}>
      <div
        style={{
          maxWidth: "min(85%, 400px)",
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
            marginBottom: visibleCount > 0 ? "10px" : 0,
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
              fontSize: "11px",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              color: "var(--text-muted)",
            }}
          >
            Working
          </span>
        </div>
        {LOADING_MESSAGES.slice(0, visibleCount).map((msg, index) => (
          <p
            key={index}
            style={{
              fontSize: "13px",
              color: "var(--text-muted)",
              margin: index > 0 ? "8px 0 0" : 0,
              lineHeight: 1.45,
            }}
          >
            {msg}
          </p>
        ))}
      </div>
    </div>
  );
}
