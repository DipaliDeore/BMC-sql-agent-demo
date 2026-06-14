from app.database import execute_query

queries = [
    ("payments total", "SELECT SUM(amount) AS t FROM payments"),
    (
        "payments completed only",
        "SELECT SUM(amount) AS t FROM payments WHERE payment_status = 'COMPLETED'",
    ),
    (
        "order_items revenue",
        "SELECT SUM(quantity * price_at_purchase) AS t FROM order_items",
    ),
    (
        "payments before apr 2026",
        "SELECT SUM(amount) AS t FROM payments WHERE payment_date < '2026-04-01'",
    ),
]
for name, q in queries:
    print(name, execute_query(q))
