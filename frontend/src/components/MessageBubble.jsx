/**
 * MessageBubble.jsx - Chat Message Component
 */

import React, { useCallback, useEffect, useState } from "react";
import ResultTable from "./ResultTable";
import SqlViewer from "./SqlViewer";
import { submitFeedback, getApiErrorMessage } from "../api/agent";

function feedbackEntryForScope(message, subIndex) {
  const list = message.feedbacks;
  if (Array.isArray(list) && list.length) {
    const hit = list.find((f) => {
      if (!f || typeof f !== "object") return false;
      if (subIndex == null) return f.sub_index == null;
      return Number(f.sub_index) === Number(subIndex);
    });
    if (hit?.vote === "up" || hit?.vote === "down") return hit;
  }
  if (subIndex == null && message.feedback?.vote) return message.feedback;
  return null;
}

function MessageFeedbackBar({ conversationId, serverMessageId, subIndex, existing }) {
  const [submitted, setSubmitted] = useState(!!existing);
  const [pickKind, setPickKind] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [note, setNote] = useState(existing ? "Thanks for your feedback." : null);

  useEffect(() => {
    setSubmitted(!!existing);
    setNote(existing ? "Thanks for your feedback." : null);
    setPickKind(false);
    setErr(null);
  }, [existing, serverMessageId, subIndex]);

  const send = useCallback(
    async (vote, failureKind = null) => {
      if (!conversationId || serverMessageId == null) return;
      setBusy(true);
      setErr(null);
      try {
        const data = await submitFeedback({
          conversationId,
          messageId: serverMessageId,
          vote,
          failureKind,
          subIndex: subIndex != null ? subIndex : null,
        });
        if (data.duplicate) {
          setNote("Feedback was already recorded.");
        } else {
          setNote("Thanks for your feedback.");
        }
        setSubmitted(true);
        setPickKind(false);
      } catch (e) {
        setErr(getApiErrorMessage(e));
      } finally {
        setBusy(false);
      }
    },
    [conversationId, serverMessageId, subIndex]
  );

  if (serverMessageId == null) return null;

  const btnBase = {
    fontFamily: "inherit",
    fontSize: "13px",
    fontWeight: 600,
    borderRadius: "8px",
    border: "1px solid var(--border)",
    background: "var(--surface-2)",
    color: "var(--text)",
    cursor: busy ? "wait" : "pointer",
    padding: "6px 12px",
    opacity: busy ? 0.65 : 1,
  };

  return (
    <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid var(--border-subtle)" }}>
      {submitted ? (
        <p style={{ margin: 0, fontSize: "12px", color: "var(--text-muted)" }}>{note || "Thanks!"}</p>
      ) : (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "12px", color: "var(--text-muted)", marginRight: "4px" }}>
              Was this helpful?
            </span>
            <button
              type="button"
              disabled={busy}
              aria-label="Thumbs up"
              onClick={() => send("up")}
              style={btnBase}
            >
              👍
            </button>
            <button
              type="button"
              disabled={busy}
              aria-label="Thumbs down"
              onClick={() => setPickKind(true)}
              style={btnBase}
            >
              👎
            </button>
          </div>
          {pickKind && (
            <div style={{ marginTop: "10px" }}>
              <p style={{ margin: "0 0 8px", fontSize: "12px", color: "var(--text-muted)" }}>
                Was the SQL wrong or the interpretation?
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => send("down", "sql")}
                  style={btnBase}
                >
                  SQL
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => send("down", "interpretation")}
                  style={btnBase}
                >
                  Interpretation
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => send("down", "other")}
                  style={btnBase}
                >
                  Not sure
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setPickKind(false)}
                  style={{ ...btnBase, borderStyle: "dashed" }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </>
      )}
      {err && (
        <p style={{ margin: "8px 0 0", fontSize: "12px", color: "var(--error)" }}>{err}</p>
      )}
    </div>
  );
}

export default function MessageBubble({ message, theme, conversationId, onSend }) {
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
              <p
                style={{
                  fontSize: "14px",
                  lineHeight: 1.65,
                  color: "var(--text)",
                  fontWeight: 600,
                  whiteSpace: "pre-line",
                }}
              >
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
                <p
                  style={{
                    fontSize: "14px",
                    lineHeight: 1.65,
                    color: "var(--text)",
                    marginBottom: "12px",
                    whiteSpace: "pre-line",
                  }}
                >
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

              <MessageFeedbackBar
                conversationId={conversationId}
                serverMessageId={message.serverMessageId}
                subIndex={index}
                existing={feedbackEntryForScope(message, index)}
              />
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
            <p
              style={{
                fontSize: "14px",
                lineHeight: 1.65,
                color: "var(--text)",
                whiteSpace: "pre-line",
              }}
            >
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

        <MessageFeedbackBar
          conversationId={conversationId}
          serverMessageId={message.serverMessageId}
          subIndex={null}
          existing={feedbackEntryForScope(message, null)}
        />
      </div>
    </div>
  );
}
