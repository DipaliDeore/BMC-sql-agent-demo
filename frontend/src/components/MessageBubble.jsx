/**
 * MessageBubble.jsx - Chat Message Component
 * --------------------------------------------
 * Renders a single message in the chat area.
 *
 * User messages:
 *   - Aligned right
 *   - Plain text of the question
 *   - Subtle background
 *
 * Assistant messages:
 *   - Aligned left
 *   - 4 sections in order:
 *     1. Explanation (plain text)
 *     2. Results Table
 *     3. SQL Query (with syntax highlighting)
 *     4. Row Count
 *
 * Error messages:
 *   - Shows "Something went wrong. Please try again."
 *
 * Props:
 *   message  {Object}  Message object with: role, content, sql, results, explanation, row_count, error
 *   theme    {string}  "dark" or "light"
 */

import React from "react";
import ResultTable from "./ResultTable";
import SqlViewer from "./SqlViewer";

export default function MessageBubble({ message, theme }) {
  const isDark = theme === "dark";
  const isUser = message.role === "user";

  // Theme colors
  const borderColor = isDark ? "#2a2a2a" : "#e5e5e5";
  const textColor = isDark ? "#e5e5e5" : "#111111";
  const mutedText = isDark ? "#999999" : "#666666";

  // ── User Message ──────────────────────────────────────────────────────
  if (isUser) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", padding: "4px 0" }}>
        <div
          style={{
            maxWidth: "70%",
            padding: "12px 16px",
            borderRadius: "12px",
            borderTopRightRadius: "4px",
            backgroundColor: isDark ? "#1a1a1a" : "#f0f0f0",
            border: `1px solid ${borderColor}`,
            fontSize: "14px",
            lineHeight: "1.5",
            color: textColor,
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  // ── Error Message ─────────────────────────────────────────────────────
  if (message.error) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-start", padding: "4px 0" }}>
        <div
          style={{
            maxWidth: "70%",
            padding: "12px 16px",
            borderRadius: "12px",
            borderTopLeftRadius: "4px",
            backgroundColor: isDark ? "#1a1a1a" : "#f5f5f5",
            border: `1px solid ${borderColor}`,
            fontSize: "14px",
            lineHeight: "1.5",
            color: isDark ? "#ef4444" : "#dc2626",
          }}
        >
          Something went wrong. Please try again.
        </div>
      </div>
    );
  }

  // ── Assistant Message ─────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", justifyContent: "flex-start", padding: "4px 0" }}>
      <div
        style={{
          maxWidth: "80%",
          padding: "16px",
          borderRadius: "12px",
          borderTopLeftRadius: "4px",
          backgroundColor: isDark ? "#1a1a1a" : "#f5f5f5",
          border: `1px solid ${borderColor}`,
          color: textColor,
        }}
      >
        {/* Section 1: Explanation */}
        {message.explanation && (
          <div style={{ marginBottom: "14px" }}>
            <p style={{ fontSize: "14px", lineHeight: "1.6" }}>
              {message.explanation}
            </p>
          </div>
        )}

        {/* Section 2: Results Table — only shown when there are results */}
        {message.results && message.results.length > 0 && (
          <div style={{ marginBottom: "14px" }}>
            <ResultTable results={message.results} theme={theme} />
          </div>
        )}

        {/* Section 3: SQL Query */}
        {message.sql && (
          <div style={{ marginBottom: "14px" }}>
            <SqlViewer sql={message.sql} theme={theme} />
          </div>
        )}

        {/* Section 4: Row Count — only shown when there are results */}
        {message.results && message.results.length > 0 && (
          <p style={{ fontSize: "13px", color: mutedText }}>
            Rows returned: {message.row_count ?? 0}
          </p>
        )}
      </div>
    </div>
  );
}