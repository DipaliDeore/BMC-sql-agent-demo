/**
 * Normalizes API chart_config (pie/bar/line) for UI components.
 * Supports legacy pie payloads: is_pie_chart + label_column + value_column.
 */

export function normalizeChartConfig(config) {
  if (!config || typeof config !== "object") return null;
  const type =
    config.chart_type ||
    (config.is_pie_chart ? "pie" : null);
  if (type !== "pie" && type !== "bar" && type !== "line") return null;
  const x = config.x_column ?? config.label_column;
  const y = config.y_column ?? config.value_column;
  if (!x || !y) return null;
  return {
    ...config,
    chart_type: type,
    x_column: x,
    y_column: y,
    is_pie_chart: type === "pie",
  };
}

export function hasRenderableChart(config) {
  return normalizeChartConfig(config) != null;
}
