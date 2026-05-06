// Generate unique key for this message
function getFeedbackStorageKey(docId, query, sql) {
  if (docId) return `fb_${docId}`
  const raw = `${(query || '').slice(0, 50)}_${(sql || '').slice(0, 50)}`
  try {
    return `fb_${btoa(encodeURIComponent(raw)).slice(0, 24)}`
  } catch {
    return `fb_${raw.replace(/[^a-z0-9]/gi, '').slice(0, 24)}`
  }
}
/**
 * MessageFeedback — visible thumbs up / down; POST /feedback
 */

import React, { useMemo, useState } from "react";
import { submitFeedback, getApiErrorMessage } from "../api/agent";

/** Executed SQL only — sent as ``sql`` so OpenSearch stores a clean query string. */
function buildSqlForFeedback(message) {
  if (!message || message.error) return "";
  if (message.is_multi && message.sub_responses?.length) {
    return message.sub_responses
      .map((s) => (s.sql || "").trim())
      .filter(Boolean)
      .join("\n\n");
  }
  return (message.sql || "").trim();
}

function buildFeedbackResponseText(message) {
  if (message.error) {
    return (message.errorText || "Something went wrong.").trim();
  }
  if (message.is_multi && message.sub_responses?.length) {
    const blocks = message.sub_responses.map((sub) =>
      [sub.question, sub.explanation, sub.result_sentence, sub.sql].filter(Boolean).join("\n")
    );
    return blocks.join("\n\n---\n\n").trim();
  }
  const text = [message.explanation, message.result_sentence, message.sql]
    .map((x) => (x == null ? "" : String(x).trim()))
    .filter(Boolean)
    .join("\n\n")
    .trim();
  if (text) return text;
  const n = message.results?.length ?? 0;
  if (n > 0) return `Returned ${n} row(s) (tabular results).`;
  return "";
}

export default function MessageFeedback({ pairedUserQuery, message }) {
  const responseText = useMemo(() => buildFeedbackResponseText(message), [message]);
  const sqlForVector = useMemo(() => buildSqlForFeedback(message), [message]);
  const queryOk = (pairedUserQuery || "").trim().length > 0;
  const responseOk = responseText.length > 0;
  const canShow = queryOk && responseOk;

  // LocalStorage-backed feedback state
  const feedbackKey = getFeedbackStorageKey(
    message?.cache_doc_id,
    pairedUserQuery,
    sqlForVector || message?.sql || ""
  );
  const [feedbackState, setFeedbackState] = useState(() => {
    try {
      return localStorage.getItem(feedbackKey) || null;
    } catch {
      return null;
    }
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function onVote(type) {
    if (feedbackState !== null || submitting) return;
    setFeedbackState(type); // Optimistic update
    try {
      localStorage.setItem(feedbackKey, type);
    } catch {}
    setSubmitting(true);
    setError(null);
    try {
      await submitFeedback(
        pairedUserQuery.trim(),
        responseText,
        type,
        { sql: sqlForVector }
      );
    } catch (err) {
      setFeedbackState(null); // Rollback on error
      try { localStorage.removeItem(feedbackKey); } catch {}
      setError(getApiErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!canShow) return null;

  return (
    <div className="msg-feedback-bar" role="group" aria-label="Rate this response">
      <span className="msg-feedback-label">Was this helpful?</span>
      {feedbackState === null && (
        <div className="msg-feedback-actions">
          <button
            type="button"
            className="msg-feedback-btn"
            onClick={() => onVote("up")}
            disabled={submitting}
            aria-label="Thumbs up — helpful"
          >
            <span className="msg-feedback-emoji" aria-hidden>
              👍
            </span>
            Helpful
          </button>
          <button
            type="button"
            className="msg-feedback-btn"
            onClick={() => onVote("down")}
            disabled={submitting}
            aria-label="Thumbs down — not helpful"
          >
            <span className="msg-feedback-emoji" aria-hidden>
              👎
            </span>
            Not helpful
          </button>
        </div>
      )}
      {feedbackState === "up" && (
        <span className="msg-feedback-thanks">
          <span className="msg-feedback-emoji" aria-hidden>
            👍
          </span>{" "}
          Thanks for the feedback.
        </span>
      )}
      {feedbackState === "down" && (
        <span className="msg-feedback-thanks">
          <span className="msg-feedback-emoji" aria-hidden>
            👎
          </span>{" "}
          Thanks — we will use this to improve.
        </span>
      )}
      {error && <span className="msg-feedback-error">{error}</span>}
    </div>
  );
}
