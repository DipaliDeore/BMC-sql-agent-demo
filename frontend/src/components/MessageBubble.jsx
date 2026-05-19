/**
 * MessageBubble.jsx - Chat Message Component
 */

import React from "react";
import { API_BASE_URL } from "../api/agent";
import ResultTable from "./ResultTable";
import SqlViewer from "./SqlViewer";
import MessageFeedback from "./MessageFeedback";
import ChartPanel from "./ChartPanel";
import AdvisoryMarkdown from "./AdvisoryMarkdown";
import { hasRenderableChart } from "./chartConfig";
import { isStrategicAdvisoryMessage, splitSqlStatements } from "./messageFormat";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import LoadingMessage from "./LoadingMessage";

function SqlStatements({ sql, theme }) {
  const statements = splitSqlStatements(sql);
  if (!statements.length) return null;

  if (statements.length === 1) {
    return (
      <div className="sql-block">
        <SqlViewer sql={statements[0]} theme={theme} />
      </div>
    );
  }

  return (
    <div className="sql-blocks-stack">
      {statements.map((stmt, index) => (
        <div key={index} className="sql-block">
          <p className="sql-block-label">Query {index + 1}</p>
          <SqlViewer sql={stmt} theme={theme} />
        </div>
      ))}
    </div>
  );
}

export default function MessageBubble({
  message,
  theme,
  pairedUserQuery = "",
  onRetry,
}) {
  const feedbackQuery = (pairedUserQuery || message.original_question || "").trim();
  const isUser = message.role === "user";
  const canShowInlineResults = !message.row_count || message.row_count <= 100;

  if (isUser) {
    const previews = message.attachmentPreviews || [];
    return (
      <div className="msg-animate msg-row-user">
        <div className="user-msg-bubble">
          {previews.length > 0 ? (
            <div
              className={`user-attachment-stack${message.content ? " user-attachment-stack--has-text" : ""}`}
            >
              {previews.map((src, i) => (
                <img
                  key={i}
                  src={src}
                  alt=""
                  className="user-attachment-thumb"
                />
              ))}
            </div>
          ) : null}
          {message.content ? <div className="user-msg-text">{message.content}</div> : null}
        </div>
      </div>
    );
  }

  if (message.streaming) {
    const n = message.streamRows?.length ?? 0;
    return (
      <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
        <div style={{ width: "100%" }}>
          {message.streamStatus && !message.streamText && (
            <>
              <div
                style={{
                  height: "70px",
                  display: "flex",
                  justifyContent: "center",
                  alignItems: "center",
                }}
              >
                <LoadingMessage />
              </div>
            </>
          )}

          {message.streamText ? (
            <AdvisoryMarkdown
              explanation={message.streamText + "▍"}
              className="msg-body markdown-wrapper"
            />
          ) : null}

          {message.streamSql ? (
            <div style={{ marginTop: "12px" }}>
              <SqlStatements sql={message.streamSql} theme={theme} />
            </div>
          ) : null}

          {n > 0 ? (
            <p style={{ fontSize: "13px", color: "var(--text-muted)", marginTop: "10px" }}>
              Received {n.toLocaleString()} row{n === 1 ? "" : "s"}…
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  if (message.error) {
    return (
      <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
        <div className="error-msg-stack">
          <div className="error-msg-inline">
            {message.errorText ||
              "Hmm, I didn't quite get that. Could you try again or rephrase?"}
          </div>
          {onRetry && feedbackQuery ? (
            <div className="error-msg-actions">
              <button
                type="button"
                className="ui-btn-secondary error-retry-btn"
                onClick={() => onRetry(feedbackQuery)}
              >
                Retry
              </button>
            </div>
          ) : null}
          <MessageFeedback pairedUserQuery={feedbackQuery} message={message} />
        </div>
      </div>
    );
  }

  // ── Multi-query assistant response
  if (message.is_multi && message.sub_responses?.length) {
    return (
      <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
        <div style={{ width: "100%" }}>
          {message.explanation && (
            <div className="msg-body markdown-wrapper" style={{ marginBottom: "1.15rem" }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.explanation}</ReactMarkdown>
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
                <div className="msg-body markdown-wrapper" style={{ marginBottom: "14px" }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{sub.explanation}</ReactMarkdown>
                </div>
              )}

              {hasRenderableChart(sub.chart_config) && sub.results && sub.results.length > 0 && (
                <ChartPanel data={sub.results} config={sub.chart_config} />
              )}

              {sub.result_sentence ? (
                <p className="msg-body" style={{ marginBottom: "14px", fontWeight: 600 }}>
                  {sub.result_sentence}
                </p>
              ) : sub.results && sub.results.length > 0 ? (
                <div style={{ marginBottom: "14px", marginTop: hasRenderableChart(sub.chart_config) ? "16px" : "0" }}>
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

          <MessageFeedback pairedUserQuery={feedbackQuery} message={message} />
        </div>
      </div>
    );
  }

  const isAdvisory = isStrategicAdvisoryMessage(message);
  const explanationText = (message.explanation || message.content || "").trim();

  return (
    <div className="msg-animate" style={{ display: "flex", justifyContent: "flex-start", width: "100%" }}>
      <div className={`assistant-msg-panel${isAdvisory ? " assistant-msg-panel--advisory" : ""}`}>
        {isAdvisory && explanationText ? (
          <AdvisoryMarkdown explanation={explanationText} />
        ) : explanationText ? (
          <div
            className="msg-body markdown-wrapper"
            style={{
              marginBottom:
                message.result_sentence || message.results?.length || message.excel_download_url
                  ? "14px"
                  : 0,
            }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{explanationText}</ReactMarkdown>
          </div>
        ) : null}

        {/* Excel Download Button */}
        {message.excel_download_url && (
          <div style={{ margin: "12px 0" }}>
            {message.row_count > 100 && (
              <p
                style={{
                  fontSize: "13px",
                  color: "var(--text-muted)",
                  marginBottom: "8px",
                  fontStyle: "italic",
                }}
              >
                {message.row_count} rows returned — too large to display in chat.
                Download the Excel file to view all results.
              </p>
            )}

            <a
              href={`${API_BASE_URL}${message.excel_download_url}`}
              download
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 16px",
                backgroundColor: "var(--accent, #4f8ef7)",
                color: "white",
                borderRadius: "6px",
                textDecoration: "none",
                fontSize: "13px",
                fontWeight: "600",
              }}
            >
              Download Excel ({message.row_count} rows)
            </a>
          </div>
        )}

        {canShowInlineResults && message.result_sentence && (
          <div className="msg-body" style={{ marginBottom: "14px", fontWeight: 600 }}>
            {message.result_sentence}
          </div>
        )}

        {hasRenderableChart(message.chart_config) &&
          message.results &&
          message.results.length > 0 && (
            <div style={{ marginBottom: "14px" }}>
              <ChartPanel data={message.results} config={message.chart_config} />
            </div>
        )}

        {canShowInlineResults &&
        !message.result_sentence &&
        message.results &&
        message.results.length > 0 && (
          <div style={{ marginBottom: "14px", marginTop: hasRenderableChart(message.chart_config) ? "16px" : "0" }}>
            <ResultTable results={message.results} />
          </div>
        )}

        {message.sql && (
          <div className={isAdvisory ? "advisory-sql-section" : ""} style={{ marginTop: isAdvisory ? "16px" : "8px" }}>
            {isAdvisory ? <p className="sql-section-label">Queries used</p> : null}
            <SqlStatements sql={message.sql} theme={theme} />
          </div>
        )}

        <MessageFeedback pairedUserQuery={feedbackQuery} message={message} />
      </div>
    </div>
  );
}