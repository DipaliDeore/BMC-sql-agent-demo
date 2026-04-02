/**
 * MessageBubble.jsx - Chat Message Component
 */

import React from "react";
import ResultTable from "./ResultTable";
import SqlViewer from "./SqlViewer";

export default function MessageBubble({ message, theme, onSend }) {
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

  // ── Multi-query assistant response: one block per sub-question ─────────────
  if (message.is_multi && message.sub_responses?.length) {
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
            <div style={{ marginBottom: "16px" }}>
              <p style={{ fontSize: "14px", lineHeight: 1.65, color: "var(--text)", fontWeight: 600 }}>
                {message.explanation}
              </p>
            </div>
          )}

          {message.sub_responses.map((sub, index) => (
            <div
              key={index}
              style={{
                marginBottom: index < message.sub_responses.length - 1 ? "20px" : 0,
                paddingBottom: index < message.sub_responses.length - 1 ? "20px" : 0,
                borderBottom:
                  index < message.sub_responses.length - 1 ? "1px solid var(--border-subtle)" : "none",
              }}
            >
              <p
                style={{
                  fontSize: "12px",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "var(--text-muted)",
                  marginBottom: "10px",
                }}
              >
                Query {index + 1}: {sub.question}
              </p>

              {sub.explanation && (
                <p style={{ fontSize: "14px", lineHeight: 1.65, color: "var(--text)", marginBottom: "12px" }}>
                  {sub.explanation}
                </p>
              )}

              {sub.result_sentence ? (
                <p style={{ fontSize: "15px", lineHeight: 1.65, fontWeight: 600, color: "var(--text)", marginBottom: "12px" }}>
                  {sub.result_sentence}
                </p>
              ) : sub.results && sub.results.length > 0 ? (
                <div style={{ marginBottom: "12px" }}>
                  <ResultTable results={sub.results} />
                </div>
              ) : (
                <p style={{ fontSize: "13px", color: "var(--text-muted)", fontStyle: "italic", marginBottom: "12px" }}>
                  No records found.
                </p>
              )}

              {sub.sql && (
                <div style={{ marginTop: "12px" }}>
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
                  <SqlViewer sql={sub.sql} theme={theme} />
                </div>
              )}


            </div>
          ))}
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
