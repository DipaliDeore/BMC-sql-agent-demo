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
      <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-end", width: "100%" }}>
        <div className="user-msg-bubble">{message.content}</div>
      </div>
    );
  }

  if (message.error) {
    return (
      <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
        <div className="error-msg-inline">
          {message.errorText ||
            "Hmm, I didn't quite get that. Could you try again or rephrase?"}
        </div>
      </div>
    );
  }

  // ── Multi-query assistant response
  if (message.is_multi && message.sub_responses?.length) {
    return (
      <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
        <div className="assistant-msg-panel" style={{ width: "100%" }}>
          {message.explanation && (
            <div className="msg-body" style={{ marginBottom: "1.15rem" }}>
              {message.explanation}
            </div>
          )}

          {message.sub_responses.map((sub, index) => (
            <div
              key={index}
              style={{
                marginBottom: index < message.sub_responses.length - 1 ? "1.75rem" : 0,
                paddingLeft: "14px",
                borderLeft: "2px solid color-mix(in srgb, var(--accent) 35%, var(--border))",
              }}
            >
              <p
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                  color: "var(--text-muted)",
                  marginBottom: "8px",
                }}
              >
                {sub.question}
              </p>

              {sub.explanation && (
                <p className="msg-body" style={{ marginBottom: "14px" }}>
                  {sub.explanation}
                </p>
              )}

              {sub.result_sentence ? (
                <p className="msg-body" style={{ marginBottom: "14px", fontWeight: 600 }}>
                  {sub.result_sentence}
                </p>
              ) : sub.results && sub.results.length > 0 ? (
                <div style={{ marginBottom: "14px" }}>
                  <ResultTable results={sub.results} />
                </div>
              ) : (
                <p style={{ fontSize: "14px", color: "var(--text-muted)", fontStyle: "italic", marginBottom: "14px" }}>
                  No records found.
                </p>
              )}

              {sub.sql && (
                <div style={{ marginTop: "12px" }}>
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
    <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
      <div className="assistant-msg-panel">
        {message.explanation && (
          <div className="msg-body" style={{ marginBottom: message.result_sentence || message.results?.length ? "14px" : 0 }}>
            {message.explanation}
          </div>
        )}

        {message.result_sentence && (
          <div className="msg-body" style={{ marginBottom: "14px", fontWeight: 600 }}>
            {message.result_sentence}
          </div>
        )}
        {!message.result_sentence && message.results && message.results.length > 0 && (
          <div style={{ marginBottom: "14px" }}>
            <ResultTable results={message.results} />
          </div>
        )}

        {message.sql && (
          <div style={{ marginTop: "8px" }}>
            <SqlViewer sql={message.sql} theme={theme} />
          </div>
        )}
      </div>
    </div>
  );
}
