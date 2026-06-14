from app.database import execute_query

print("returns:", execute_query("SELECT COUNT(*) AS c FROM returns WHERE return_date IS NOT NULL"))
print("refunds:", execute_query("SELECT COUNT(*) AS c FROM refunds"))
print(
    "refund months:",
    execute_query(
        "SELECT DATE_FORMAT(r.return_date, '%Y-%m') AS m, SUM(f.refund_amount) AS t "
        "FROM refunds f JOIN returns r ON r.return_id = f.return_id "
        "WHERE r.return_date IS NOT NULL GROUP BY m ORDER BY m LIMIT 5"
    ),
)
