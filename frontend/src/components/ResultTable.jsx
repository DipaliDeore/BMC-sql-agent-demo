/**
 * ResultTable.jsx - Results Table Component
 */

import React from "react";

export default function ResultTable({ results }) {
  if (!results || results.length === 0) {
    return (
      <p
        style={{
          fontSize: "13px",
          color: "var(--text-muted)",
          fontStyle: "italic",
          padding: "8px 0",
        }}
      >
        No records found.
      </p>
    );
  }

  const columns = Object.keys(results[0]);

  return (
    <div
      style={{
        overflowX: "auto",
        borderRadius: "10px",
        border: "1px solid var(--border)",
        backgroundColor: "var(--surface-1)",
      }}
    >
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "13px",
        }}
      >
        <thead>
          <tr style={{ backgroundColor: "var(--surface-2)" }}>
            {columns.map((col) => (
              <th
                key={col}
                style={{
                  textAlign: "left",
                  padding: "11px 16px",
                  fontWeight: 600,
                  fontSize: "11px",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  color: "var(--text-muted)",
                  borderBottom: "1px solid var(--border)",
                  whiteSpace: "nowrap",
                }}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {results.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              style={{
                backgroundColor:
                  rowIndex % 2 === 0 ? "var(--surface-1)" : "var(--surface-2)",
              }}
            >
              {columns.map((col) => (
                <td
                  key={col}
                  style={{
                    padding: "9px 16px",
                    color: "var(--text)",
                    borderBottom: "1px solid var(--border-subtle)",
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
