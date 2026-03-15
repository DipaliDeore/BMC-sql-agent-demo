/**
 * LoadingMessage.jsx - Sequential Loading Status Component
 * ---------------------------------------------------------
 * Shows 3 plain-text status messages with 1-second delay each:
 *   1. "Analyzing question..."
 *   2. "Generating SQL query..."
 *   3. "Fetching results..."
 *
 * No spinners, no animations — plain text only.
 *
 * Props:
 *   theme  {string}  "dark" or "light"
 */

import React, { useState, useEffect } from "react";

// The 3 loading messages shown sequentially
const LOADING_MESSAGES = [
  "Analyzing question...",
  "Generating SQL query...",
  "Fetching results...",
];

export default function LoadingMessage({ theme }) {
  const isDark = theme === "dark";

  // Track which messages are visible (start with just the first one)
  const [visibleCount, setVisibleCount] = useState(1);

  // Show each message one at a time with a 1-second delay
  useEffect(() => {
    if (visibleCount < LOADING_MESSAGES.length) {
      const timer = setTimeout(() => {
        setVisibleCount((prev) => prev + 1);
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [visibleCount]);

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "flex-start",
        padding: "4px 0",
      }}
    >
      <div
        style={{
          maxWidth: "70%",
          padding: "12px 16px",
          borderRadius: "12px",
          borderTopLeftRadius: "4px",
          backgroundColor: isDark ? "#1a1a1a" : "#f5f5f5",
          border: `1px solid ${isDark ? "#2a2a2a" : "#e5e5e5"}`,
        }}
      >
        {LOADING_MESSAGES.slice(0, visibleCount).map((msg, index) => (
          <p
            key={index}
            style={{
              fontSize: "13px",
              color: isDark ? "#999999" : "#666666",
              margin: index > 0 ? "6px 0 0" : 0,
              lineHeight: "1.4",
            }}
          >
            {msg}
          </p>
        ))}
      </div>
    </div>
  );
}
