import sys
import os

sys.path.append(r"d:\BMC_Internship\BMC_Insight_Finder\BMC-sql-agent-demo\backend")
from app.agent_executor import generate_and_execute_with_tools

schema = """
CREATE TABLE categories (
    category_id INT PRIMARY KEY,
    name VARCHAR(255)
);
CREATE TABLE products (
    product_id INT PRIMARY KEY,
    name VARCHAR(255),
    category_id INT
);
CREATE TABLE order_items (
    order_id INT,
    product_id INT,
    quantity INT,
    price DECIMAL(10, 2)
);
"""

result = generate_and_execute_with_tools("show me revenue by category in a bar chart", schema)
print("Result:")
print(result)
