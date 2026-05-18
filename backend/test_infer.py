import json
from app.chart_inference import infer_chart_config

plan = {"needs_chart": True, "chart_hint": "pie"}
rows = [{"TOTAL_SALES": 7000, "CATEGORY_NAME": "Kitchen Appliances"}]

cfg = infer_chart_config(plan, rows)
print("Inferred config:", cfg)
