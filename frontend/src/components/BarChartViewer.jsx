import React, { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const TOOLTIP_BOX = {
  borderRadius: "8px",
  border: "none",
  boxShadow: "0 4px 12px rgba(0,0,0,0.1)",
  background: "var(--surface-1)",
  color: "var(--text)",
};

function parseY(raw) {
  if (raw == null) return NaN;
  if (typeof raw === "number") return raw;
  if (typeof raw === "string") return parseFloat(raw.replace(/[^0-9.-]+/g, ""));
  return NaN;
}

export default function BarChartViewer({ data, config }) {
  const xKey = config?.x_column;
  const yKey = config?.y_column;
  const y2Key = (config?.y_column_2 || "").trim() || null;

  const chartData = useMemo(() => {
    if (!data?.length || !xKey || !yKey) return [];
    return data
      .map((row) => {
        const name = row[xKey] != null ? String(row[xKey]) : "";
        const v1 = parseY(row[yKey]);
        const point = { name, [yKey]: v1 };
        if (y2Key) {
          point[y2Key] = parseY(row[y2Key]);
        }
        return point;
      })
      .filter((d) => {
        if (d.name === "") return false;
        const ok1 = !Number.isNaN(d[yKey]);
        if (!y2Key) return ok1;
        const ok2 = !Number.isNaN(d[y2Key]);
        return ok1 || ok2;
      });
  }, [data, xKey, yKey, y2Key]);

  if (!chartData.length) {
    return (
      <div
        style={{
          padding: "20px",
          textAlign: "center",
          color: "var(--text-muted)",
          background: "var(--surface-1)",
          borderRadius: "var(--radius-md)",
        }}
      >
        {y2Key
          ? `Could not build a bar chart from '${xKey}', '${yKey}', and '${y2Key}'.`
          : `Could not build a bar chart from columns '${xKey}' and '${yKey}'.`}
      </div>
    );
  }

  const dense = chartData.length > 12;

  return (
    <div
      style={{
        width: "100%",
        height: 380,
        background: "var(--surface-0)",
        borderRadius: "var(--radius-md)",
        padding: "16px",
        boxShadow: "var(--shadow-sm)",
        border: "1px solid var(--border)",
        marginTop: "12px",
      }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 12, left: 4, bottom: dense ? 48 : 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.6} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            interval={dense ? "preserveStartEnd" : 0}
            angle={dense ? -32 : 0}
            textAnchor={dense ? "end" : "middle"}
            height={dense ? 72 : 36}
            tickFormatter={(v) => (String(v).length > 24 ? `${String(v).slice(0, 22)}…` : v)}
          />
          <YAxis tick={{ fontSize: 11, fill: "var(--text-muted)" }} width={48} />
          <Tooltip contentStyle={TOOLTIP_BOX} itemStyle={{ color: "var(--text)" }} />
          <Legend wrapperStyle={{ fontSize: "13px", color: "var(--text)" }} />
          <Bar dataKey={yKey} name={yKey} fill="#2563eb" radius={[4, 4, 0, 0]} maxBarSize={y2Key ? 28 : 56} />
          {y2Key ? (
            <Bar dataKey={y2Key} name={y2Key} fill="#0d9488" radius={[4, 4, 0, 0]} maxBarSize={28} />
          ) : null}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
