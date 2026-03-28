/**
 * SqlViewer.jsx - SQL Code Display Component
 */

import React from "react";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import sql from "react-syntax-highlighter/dist/esm/languages/hljs/sql";
import { vs, vs2015 } from "react-syntax-highlighter/dist/esm/styles/hljs";

SyntaxHighlighter.registerLanguage("sql", sql);

export default function SqlViewer({ sql: sqlCode, theme }) {
  const isDark = theme === "dark";
  const highlighterTheme = isDark ? vs2015 : vs;

  return (
    <SyntaxHighlighter
      language="sql"
      style={highlighterTheme}
      customStyle={{
        borderRadius: "10px",
        padding: "14px 16px",
        fontSize: "13px",
        fontFamily: '"JetBrains Mono", ui-monospace, monospace',
        border: "1px solid var(--border)",
        margin: 0,
        background: isDark ? "#1e1e1e" : "#fafafa",
      }}
      wrapLongLines={true}
    >
      {sqlCode}
    </SyntaxHighlighter>
  );
}
