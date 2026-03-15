/**
 * SqlViewer.jsx - SQL Code Display Component
 * --------------------------------------------
 * Displays the generated SQL query with syntax highlighting.
 *
 * Uses react-syntax-highlighter:
 *   - "vs" theme for light mode
 *   - "vs2015" theme for dark mode
 *
 * Props:
 *   sql    {string}  The SQL query string to display
 *   theme  {string}  "dark" or "light"
 */

import React from "react";
import { Light as SyntaxHighlighter } from "react-syntax-highlighter";
import sql from "react-syntax-highlighter/dist/esm/languages/hljs/sql";
import { vs, vs2015 } from "react-syntax-highlighter/dist/esm/styles/hljs";

// Register SQL language for syntax highlighting
SyntaxHighlighter.registerLanguage("sql", sql);

export default function SqlViewer({ sql: sqlCode, theme }) {
  const isDark = theme === "dark";

  // Choose the theme based on dark/light mode
  const highlighterTheme = isDark ? vs2015 : vs;

  return (
    <div>
      {/* Section heading */}
      <p
        style={{
          fontSize: "12px",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: isDark ? "#888888" : "#666666",
          marginBottom: "6px",
        }}
      >
        Generated SQL
      </p>

      {/* SQL code block */}
      <SyntaxHighlighter
        language="sql"
        style={highlighterTheme}
        customStyle={{
          borderRadius: "6px",
          padding: "14px",
          fontSize: "13px",
          border: `1px solid ${isDark ? "#2a2a2a" : "#e5e5e5"}`,
          margin: 0,
        }}
        wrapLongLines={true}
      >
        {sqlCode}
      </SyntaxHighlighter>
    </div>
  );
}
