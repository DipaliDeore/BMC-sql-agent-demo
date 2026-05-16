/**
 * Markdown body for strategic / advisory answers with readable paragraphs.
 */

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { formatMarkdownParagraphs, splitAssumptionFootnote } from "./messageFormat";

export default function AdvisoryMarkdown({
  explanation,
  className = "msg-body markdown-wrapper",
}) {
  const { body, footnote } = splitAssumptionFootnote(explanation);
  const markdown = formatMarkdownParagraphs(body);

  if (!markdown && !footnote) return null;

  return (
    <div className="advisory-markdown">
      {markdown ? (
        <div className={className}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </div>
      ) : null}
      {footnote ? (
        <p className="advisory-footnote">
          <span className="advisory-footnote-label">Assumption used:</span> {footnote}
        </p>
      ) : null}
    </div>
  );
}
