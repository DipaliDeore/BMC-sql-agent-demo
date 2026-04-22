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
  // feedbackState: null (not given), "up", "down"
  const [feedbackState, setFeedbackState] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const responseText = useMemo(() => buildFeedbackResponseText(message), [message]);
  const sqlForVector = useMemo(() => buildSqlForFeedback(message), [message]);
  const queryOk = (pairedUserQuery || "").trim().length > 0;
  const responseOk = responseText.length > 0;
  const canShow = queryOk && responseOk;

  async function onVote(type) {
    if (feedbackState !== null) return; // Already voted
    setFeedbackState(type); // Optimistic update
    setError(null);
    setSubmitting(true);
    try {
      await submitFeedback(pairedUserQuery.trim(), responseText, type, { sql: sqlForVector });
    } catch (err) {
      setFeedbackState(null); // Reset on error
      setError(getApiErrorMessage(err));
      console.error("Feedback failed:", err);
    } finally {
      setSubmitting(false);
    }
  }

  if (!canShow) return null;

  return (
    <div className="msg-feedback-bar" role="group" aria-label="Rate this response">
      <span className="msg-feedback-label">Was this helpful?</span>
      {feedbackState === null && (
        <div className="feedback-buttons">
          <button onClick={() => onVote("up")} disabled={submitting}>👍</button>
          <button onClick={() => onVote("down")} disabled={submitting}>👎</button>
        </div>
      )}
      {feedbackState === "up" && <span>👍 Thanks!</span>}
      {feedbackState === "down" && <span>👎 Noted!</span>}
      {error && <span className="msg-feedback-error">{error}</span>}
    </div>
  );
}
