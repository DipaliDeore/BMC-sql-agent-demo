"""Quick E2E forecast test with mocked LLM."""
from unittest.mock import MagicMock, patch

from app.forecast_pipeline import execute_forecast_pipeline

SCHEMA = """Table: payments (payment_id, order_id, amount, payment_date, payment_status)
Table: orders (order_id, customer_id, order_date, total_amount)"""

SQL = (
    "SELECT DATE_FORMAT(payment_date, '%Y-%m') AS payment_month, "
    "SUM(amount) AS total_revenue FROM payments WHERE payment_date IS NOT NULL "
    "GROUP BY payment_month ORDER BY payment_month ASC"
)

mock_resp = MagicMock()
mock_resp.content = f'{{"queries": ["{SQL}"]}}'

with patch("app.forecast_pipeline.invoke_with_retry", return_value=mock_resp):
    result = execute_forecast_pipeline("Predict revenue for the next 3 months", SCHEMA)

print("status:", result.get("status") if result else None)
print("response_kind:", result.get("response_kind") if result else None)
print("row_count:", result.get("row_count") if result else None)
print("explanation:", (result.get("explanation") or "")[:300] if result else None)
print("chart:", result.get("chart_config") if result else None)
