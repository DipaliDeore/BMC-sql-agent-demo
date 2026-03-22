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
 * Assistant messages (STRICT response rules):
 *   - Single value (COUNT/SUM/AVG): natural language sentence only, NO table, NO column names
 *   - Multiple rows/columns: tabular format
 *   - Executed Query always at the end
 *   Order: Explanation → (sentence OR table) → Executed Query
 *
 * Error messages:
 *   - Shows a human-friendly error from errorText, or a default gentle message
 *
 * Props:
 *   message  {Object}  Message object with: role, content, sql, results, explanation, row_count, result_sentence, error, errorText
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
          {message.errorText ||
            "Hmm, I didn't quite get that. Could you try again or rephrase?"}
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

        {/* Section 1.5: Retrieved cached references (optional) */}
        {message.cache_references && message.cache_references.length > 0 && (
          <div style={{ marginBottom: "14px" }}>
            <p style={{ fontSize: "12px", color: mutedText, marginBottom: "6px", fontWeight: 600 }}>
              Retrieved Similar Cached Questions
            </p>
            {message.cache_references.map((ref, idx) => (
              <div key={idx} style={{ fontSize: "12px", lineHeight: "1.5", color: isDark ? "#d1d5db" : "#374151" }}>
                {idx + 1}. score: {ref.score} | past question: {ref.question}
              </div>
            ))}
          </div>
        )}

        {/* Section 2: Single value = natural language sentence only. Multiple rows/columns = table */}
        {message.result_sentence && (
          <div style={{ marginBottom: "14px" }}>
            <p style={{ fontSize: "15px", lineHeight: "1.6", fontWeight: 500 }}>
              {message.result_sentence}
            </p>
          </div>
        )}
        {!message.result_sentence && message.results && message.results.length > 0 && (
          <div style={{ marginBottom: "14px" }}>
            <ResultTable results={message.results} theme={theme} />
          </div>
        )}

        {/* Section 3: Executed Query — fixed nesting here */}
        {message.sql && (
          <div style={{ marginTop: "14px", paddingTop: "14px", borderTop: `1px solid ${borderColor}` }}>
            <p style={{ fontSize: "12px", color: mutedText, marginBottom: "6px", fontWeight: 600 }}>
              Executed Query:
            </p>
            <SqlViewer sql={message.sql} theme={theme} />
          </div>
        )}
      </div>
    </div>
  );
}