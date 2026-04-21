/**
 * MessageFeedback — visible thumbs up / down; POST /feedback
 */

import React, { useMemo, useState, useCallback } from "react";
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
  const [choice, setChoice] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const responseText = useMemo(() => buildFeedbackResponseText(message), [message]);
  const sqlForVector = useMemo(() => buildSqlForFeedback(message), [message]);
  const queryOk = (pairedUserQuery || "").trim().length > 0;
  const responseOk = responseText.length > 0;
  const canShow = queryOk && responseOk;

  const onVote = useCallback(
    async (feedback) => {
      if (!canShow || submitting || choice) return;
      setError(null);
      setSubmitting(true);
      try {
        await submitFeedback(pairedUserQuery.trim(), responseText, feedback, {
          sql: sqlForVector || undefined,
        });
        setChoice(feedback);
      } catch (e) {
        setError(getApiErrorMessage(e));
      } finally {
        setSubmitting(false);
      }
    },
    [pairedUserQuery, responseText, sqlForVector, canShow, submitting, choice]
  );

  if (!canShow) return null;

  const upActive = choice === "up";
  const downActive = choice === "down";
  const disabled = submitting || !!choice;

  return (
    <div className="msg-feedback-bar" role="group" aria-label="Rate this response">
      <span className="msg-feedback-label">Was this helpful?</span>
      <div className="msg-feedback-actions">
        <button
          type="button"
          className={`msg-feedback-btn${upActive ? " msg-feedback-btn--up-active" : ""}`}
          onClick={() => onVote("up")}
          disabled={disabled}
          aria-pressed={upActive}
          aria-label="Thumbs up — helpful"
        >
          <span className="msg-feedback-emoji" aria-hidden>
            👍
          </span>
          <span>Helpful</span>
        </button>
        <button
          type="button"
          className={`msg-feedback-btn${downActive ? " msg-feedback-btn--down-active" : ""}`}
          onClick={() => onVote("down")}
          disabled={disabled}
          aria-pressed={downActive}
          aria-label="Thumbs down — not helpful"
        >
          <span className="msg-feedback-emoji" aria-hidden>
            👎
          </span>
          <span>Not helpful</span>
        </button>
      </div>
      {choice && <span className="msg-feedback-thanks">Thanks for the feedback.</span>}
      {error && <span className="msg-feedback-error">{error}</span>}
    </div>
  );
}
