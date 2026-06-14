from app.database import execute_query

queries = [
    ("total payments", "SELECT SUM(amount) AS total FROM payments"),
    ("count", "SELECT COUNT(*) AS c FROM payments"),
    ("max id", "SELECT MAX(payment_id) AS m FROM payments"),
    (
        "apr2026",
        "SELECT SUM(amount) AS t FROM payments "
        "WHERE payment_date >= '2026-04-01' AND payment_date < '2026-05-01'",
    ),
    (
        "ids 31-60",
        "SELECT payment_id, amount, payment_date FROM payments "
        "WHERE payment_id BETWEEN 31 AND 60 ORDER BY payment_id",
    ),
    (
        "by month 2026",
        "SELECT DATE_FORMAT(payment_date, '%Y-%m') AS m, SUM(amount) AS t "
        "FROM payments GROUP BY m ORDER BY m",
    ),
]
for name, q in queries:
    print(name, execute_query(q))
