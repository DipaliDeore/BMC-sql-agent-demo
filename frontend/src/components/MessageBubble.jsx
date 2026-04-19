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
      <div style={{ display: "flex", justifyContent: "flex-end", width: "100%" }}>
        <div
          style={{
            maxWidth: "70%",
            padding: "10px 16px",
            borderRadius: "20px",
            backgroundColor: "var(--user-bubble)",
            border: "1px solid var(--user-bubble-border)",
            fontSize: "15px",
            lineHeight: 1.5,
            color: "var(--text)",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  if (message.error) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
        <div
          style={{
            maxWidth: "85%",
            padding: "12px 0",
            fontSize: "14.5px",
            lineHeight: 1.6,
            color: "var(--error)",
          }}
        >
          {message.errorText ||
            "Hmm, I didn't quite get that. Could you try again or rephrase?"}
        </div>
      </div>
    );
  }

  // ── Multi-query assistant response
  if (message.is_multi && message.sub_responses?.length) {
    return (
      <div style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
        <div style={{ width: "100%", padding: "12px 0", color: "var(--text)" }}>
          {message.explanation && (
            <div style={{ marginBottom: "20px" }}>
              <p style={{ fontSize: "15px", lineHeight: 1.6, color: "var(--text)" }}>
                {message.explanation}
              </p>
            </div>
          )}

          {message.sub_responses.map((sub, index) => (
            <div
              key={index}
              style={{
                marginBottom: "32px",
                paddingLeft: "16px",
                borderLeft: "2px solid var(--border)",
              }}
            >
              <p
                style={{
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "var(--text-muted)",
                  marginBottom: "8px",
                }}
              >
                {sub.question}
              </p>

              {sub.explanation && (
                <p style={{ fontSize: "15px", lineHeight: 1.6, color: "var(--text)", marginBottom: "16px" }}>
                  {sub.explanation}
                </p>
              )}

              {sub.result_sentence ? (
                <p style={{ fontSize: "15px", lineHeight: 1.6, fontWeight: 500, color: "var(--text)", marginBottom: "16px" }}>
                  {sub.result_sentence}
                </p>
              ) : sub.results && sub.results.length > 0 ? (
                <div style={{ marginBottom: "16px" }}>
                  <ResultTable results={sub.results} />
                </div>
              ) : (
                <p style={{ fontSize: "14px", color: "var(--text-muted)", fontStyle: "italic", marginBottom: "16px" }}>
                  No records found.
                </p>
              )}

              {sub.sql && (
                <div style={{ marginTop: "16px" }}>
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
    <div style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
      <div style={{ width: "100%", padding: "12px 0", color: "var(--text)" }}>
        {message.explanation && (
          <div style={{ marginBottom: "16px" }}>
            <p style={{ fontSize: "15px", lineHeight: 1.6, color: "var(--text)" }}>
              {message.explanation}
            </p>
          </div>
        )}

        {message.result_sentence && (
          <div style={{ marginBottom: "16px" }}>
            <p style={{ fontSize: "15px", lineHeight: 1.6, fontWeight: 500, color: "var(--text)" }}>
              {message.result_sentence}
            </p>
          </div>
        )}
        {!message.result_sentence && message.results && message.results.length > 0 && (
          <div style={{ marginBottom: "16px" }}>
            <ResultTable results={message.results} />
          </div>
        )}

        {message.sql && (
          <div style={{ marginTop: "20px" }}>
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
