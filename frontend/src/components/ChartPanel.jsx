import React from "react";
import { normalizeChartConfig } from "./chartConfig";
import PieChartViewer from "./PieChartViewer";
import BarChartViewer from "./BarChartViewer";
import LineChartViewer from "./LineChartViewer";

/**
 * Renders pie, bar, or line chart from normalized chart_config + result rows.
 */
export default function ChartPanel({ data, config }) {
  const c = normalizeChartConfig(config);
  if (!c || !data?.length) return null;

  switch (c.chart_type) {
    case "pie":
      return <PieChartViewer data={data} config={c} />;
    case "bar":
      return <BarChartViewer data={data} config={c} />;
    case "line":
      return <LineChartViewer data={data} config={c} />;
    default:
      return null;
  }
}
