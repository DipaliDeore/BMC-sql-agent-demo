/**
 * ResultTable.jsx - Results Table Component
 * -------------------------------------------
 * Renders query results as an HTML table.
 *
 * Features:
 *   - Header row from object keys
 *   - Alternating row colors for readability
 *   - Shows "No records found." if results array is empty
 *
 * Props:
 *   results  {Array<Object>}  Array of row objects from the API
 *   theme    {string}         "dark" or "light"
 */

import React from "react";

export default function ResultTable({ results, theme }) {
  const isDark = theme === "dark";

  // If results is empty, show empty message
  if (!results || results.length === 0) {
    return (
      <p
        style={{
          fontSize: "13px",
          color: isDark ? "#888888" : "#666666",
          fontStyle: "italic",
          padding: "8px 0",
        }}
      >
        No records found.
      </p>
    );
  }

  // Get column names from the first result object
  const columns = Object.keys(results[0]);

  // Table styles
  const tableBorder = isDark ? "#2a2a2a" : "#e5e5e5";
  const headerBg = isDark ? "#1a1a1a" : "#f5f5f5";
  const headerText = isDark ? "#e5e5e5" : "#111111";
  const evenRowBg = isDark ? "#141414" : "#ffffff";
  const oddRowBg = isDark ? "#1a1a1a" : "#fafafa";
  const cellText = isDark ? "#cccccc" : "#333333";

  return (
    <div style={{ overflowX: "auto", borderRadius: "6px", border: `1px solid ${tableBorder}` }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "13px",
        }}
      >
        {/* Table header */}
        <thead>
          <tr style={{ backgroundColor: headerBg }}>
            {columns.map((col) => (
              <th
                key={col}
                style={{
                  textAlign: "left",
                  padding: "10px 14px",
                  fontWeight: 600,
                  fontSize: "12px",
                  color: headerText,
                  borderBottom: `1px solid ${tableBorder}`,
                  whiteSpace: "nowrap",
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>

        {/* Table body with alternating row colors */}
        <tbody>
          {results.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              style={{
                backgroundColor: rowIndex % 2 === 0 ? evenRowBg : oddRowBg,
              }}
            >
              {columns.map((col) => (
                <td
                  key={col}
                  style={{
                    padding: "8px 14px",
                    color: cellText,
                    borderBottom: `1px solid ${tableBorder}`,
                    whiteSpace: "nowrap",
                  }}
                >
                  {String(row[col] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
