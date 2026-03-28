/**
 * MessageBubble.jsx - Chat Message Component
 */

import React from "react";
import ResultTable from "./ResultTable";
import SqlViewer from "./SqlViewer";

export default function MessageBubble({ message, theme }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end", padding: "2px 0" }}>
        <div
          style={{
            maxWidth: "min(85%, 640px)",
            padding: "12px 16px",
            borderRadius: "14px",
            borderTopRightRadius: "4px",
            backgroundColor: "var(--user-bubble)",
            border: "1px solid var(--user-bubble-border)",
            fontSize: "14px",
            lineHeight: 1.55,
            color: "var(--text)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  if (message.error) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-start", padding: "2px 0" }}>
        <div
          style={{
            maxWidth: "min(85%, 640px)",
            padding: "14px 16px",
            borderRadius: "14px",
            borderTopLeftRadius: "4px",
            backgroundColor: "var(--error-bg)",
            border: "1px solid var(--border)",
            fontSize: "14px",
            lineHeight: 1.55,
            color: "var(--error)",
          }}
        >
          {message.errorText ||
            "Hmm, I didn't quite get that. Could you try again or rephrase?"}
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", justifyContent: "flex-start", padding: "2px 0" }}>
      <div
        style={{
          maxWidth: "min(92%, 800px)",
          padding: "18px 20px",
          borderRadius: "14px",
          borderTopLeftRadius: "4px",
          backgroundColor: "var(--assistant-bubble)",
          border: "1px solid var(--border)",
          color: "var(--text)",
          boxShadow: "var(--shadow-md)",
        }}
      >
        {message.explanation && (
          <div style={{ marginBottom: "14px" }}>
            <p style={{ fontSize: "14px", lineHeight: 1.65, color: "var(--text)" }}>
              {message.explanation}
            </p>
          </div>
        )}

        {message.cache_references && message.cache_references.length > 0 && (
          <div
            style={{
              marginBottom: "14px",
              padding: "12px 14px",
              borderRadius: "10px",
              backgroundColor: "var(--surface-2)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <p
              style={{
                fontSize: "11px",
                color: "var(--text-muted)",
                marginBottom: "8px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              Similar cached questions
            </p>
            {message.cache_references.map((ref, idx) => (
              <div
                key={idx}
                style={{
                  fontSize: "12px",
                  lineHeight: 1.5,
                  color: "var(--text-muted)",
                  marginTop: idx ? "6px" : 0,
                }}
              >
                <span style={{ fontWeight: 600, color: "var(--text)" }}>{idx + 1}.</span>{" "}
                score {ref.score} — {ref.question}
              </div>
            ))}
          </div>
        )}

        {message.result_sentence && (
          <div style={{ marginBottom: "14px" }}>
            <p style={{ fontSize: "15px", lineHeight: 1.65, fontWeight: 600, color: "var(--text)" }}>
              {message.result_sentence}
            </p>
          </div>
        )}
        {!message.result_sentence && message.results && message.results.length > 0 && (
          <div style={{ marginBottom: "14px" }}>
            <ResultTable results={message.results} />
          </div>
        )}

        {message.sql && (
          <div
            style={{
              marginTop: "16px",
              paddingTop: "16px",
              borderTop: "1px solid var(--border-subtle)",
            }}
          >
            <p
              style={{
                fontSize: "11px",
                color: "var(--text-muted)",
                marginBottom: "8px",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              Executed query
            </p>
            <SqlViewer sql={message.sql} theme={theme} />
          </div>
        )}
      </div>
    </div>
  );
}
