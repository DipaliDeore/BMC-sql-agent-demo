"""Audit which pipeline each demo question routes to."""
from app.question_planner import build_question_plan
from app.forecast_pipeline import should_use_forecast_pipeline
from app.what_if_pipeline import should_use_what_if_pipeline
from app.strategic_pipeline import should_use_strategic_pipeline
from app.trend_pipeline import should_use_trend_pipeline

SCHEMA = """Table: orders (order_id, customer_id, order_date, total_amount, order_status)
Table: order_items (order_item_id, order_id, product_id, quantity, price_at_purchase)
Table: payments (payment_id, order_id, amount, payment_date, payment_status)
Table: products (product_id, name, category_id)
Table: customers (customer_id, name, email)
Table: warehouse_inventory (product_id, warehouse_id, stock)
Table: returns (return_id, order_id, product_id)
Table: refunds (refund_id, order_id, refund_amount)"""

QUESTIONS = [
    "What will my revenue be next month based on historical trends?",
    "Predict revenue for the next 3 months.",
    "Estimate sales for Q4 2027.",
    "What is the expected annual revenue for next year?",
    "Show projected monthly revenue for the next 12 months.",
    "If revenue continues growing at the current rate, what will revenue be in 6 months?",
    "What will revenue look like if sales increase by 15% every month?",
    "How much revenue can we expect if order volume grows by 20%?",
    "What happens if average order value increases by 10%?",
    "Which products are likely to run out of stock next month?",
    "How much inventory should I order for the next quarter?",
    "Predict stock requirements for top-selling products.",
    "How many customers are expected to place orders next month?",
    "Predict customer growth for the next 6 months.",
    "Which customers are likely to become repeat buyers?",
    "Predict the number of returns next month.",
    "Estimate refund costs for the next quarter.",
    "Which products are expected to be top sellers next month?",
    "Predict demand for each product category.",
    "What should I do to increase revenue by 20% next quarter?",
    "What will revenue be next year if sales increase by 10% every quarter?",
    "What if returns decrease by 25%? How will profit change?",
]

for q in QUESTIONS:
    plan = build_question_plan(q, SCHEMA)
    fc = should_use_forecast_pipeline(q, plan)
    wi = should_use_what_if_pipeline(q, plan)
    st = should_use_strategic_pipeline(q, plan)
    tr = should_use_trend_pipeline(q, plan)
    if plan.get("strategy") == "deterministic_sql":
        route = "DETERMINISTIC"
    elif fc:
        route = "FORECAST"
    elif tr:
        route = "TREND"
    elif wi:
        route = "WHAT_IF"
    elif st:
        route = "STRATEGIC"
    else:
        route = "GENERIC"
    print(
        f"{route:12} | fc={int(fc)} wi={int(wi)} st={int(st)} tr={int(tr)} "
        f"| {plan.get('strategy')} | {q[:65]}"
    )
