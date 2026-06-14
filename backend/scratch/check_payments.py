from app.database import execute_query

r = execute_query(
    """
    SELECT DATE_FORMAT(payment_date, '%Y-%m') AS payment_month,
           COUNT(*) AS row_count,
           SUM(amount) AS total_payment_amount
    FROM payments
    WHERE payment_date IS NOT NULL
    GROUP BY payment_month
    ORDER BY payment_month
    """
)
if isinstance(r, dict) and "error" in r:
    print("ERROR:", r)
else:
    print("month_count:", len(r))
    for row in r:
        print(row)
