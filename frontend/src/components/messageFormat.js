/**
 * Helpers for rendering assistant messages (markdown + SQL).
 */

/** Ensure markdown gets paragraph breaks (single newlines → space collapse in MD). */
export function formatMarkdownParagraphs(text) {
  if (!text) return "";
  const normalized = String(text).replace(/\r\n/g, "\n").trim();
  if (!normalized) return "";

  const blocks = normalized.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  if (blocks.length > 1) {
    return blocks.join("\n\n");
  }

  // One block with single newlines: treat blank-line-like sentence breaks as paragraphs.
  return normalized
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n\n");
}

/** Pull trailing "Assumption used: …" into a footnote for cleaner layout. */
export function splitAssumptionFootnote(explanation) {
  const raw = (explanation || "").trim();
  if (!raw) return { body: "", footnote: null };

  const marker = /(\n\n|\n)Assumption used:\s*/i;
  const match = raw.match(marker);
  if (!match || match.index == null) {
    return { body: raw, footnote: null };
  }

  const body = raw.slice(0, match.index).trim();
  const footnote = raw.slice(match.index + match[0].length).trim();
  return { body, footnote: footnote || null };
}

/** Split combined SQL (multiple SELECTs) for separate viewers. */
export function splitSqlStatements(sql) {
  const raw = (sql || "").trim();
  if (!raw) return [];

  const parts = raw
    .split(/;\s*(?=(?:SELECT|WITH)\b)/i)
    .map((s) => s.trim().replace(/;+\s*$/, ""))
    .filter(Boolean);

  return parts.length > 0 ? parts : [raw];
}

export function isStrategicAdvisoryMessage(message) {
  if (!message || message.role !== "assistant" || message.error) return false;
  if (message.response_kind === "strategic_advisory") return true;
  const expl = (message.explanation || message.content || "").trim();
  const hasSql = Boolean((message.sql || "").trim());
  const noTable =
    !message.is_multi &&
    (!message.results || message.results.length === 0) &&
    !(message.row_count > 0);
  return hasSql && noTable && expl.length > 120;
}
