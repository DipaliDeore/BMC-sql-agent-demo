"""
schema_snapshot.py — Fetch and hash MySQL/TiDB schema (tables, columns, FK graph).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app import config

# pyrefly: ignore [missing-import]
from mysql.connector import Error

from app.database import get_db_connection


@dataclass
class ForeignKeyEdge:
    table_name: str
    column_name: str
    referenced_table: str
    referenced_column: str


@dataclass
class TableInfo:
    name: str
    columns: list[str] = field(default_factory=list)


@dataclass
class SchemaSnapshot:
    tables: list[TableInfo]
    relationships: list[ForeignKeyEdge]
    text: str
    content_hash: str
    graph: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "tables": [
                {"name": t.name, "columns": list(t.columns)} for t in self.tables
            ],
            "relationships": [
                {
                    "table_name": r.table_name,
                    "column_name": r.column_name,
                    "referenced_table": r.referenced_table,
                    "referenced_column": r.referenced_column,
                }
                for r in self.relationships
            ],
            "graph": self.graph,
        }


def _canonical_payload(tables: list[TableInfo], relationships: list[ForeignKeyEdge]) -> str:
    table_part = [
        {"name": t.name, "columns": sorted(t.columns)}
        for t in sorted(tables, key=lambda x: x.name.lower())
    ]
    rel_part = sorted(
        [
            {
                "table_name": r.table_name,
                "column_name": r.column_name,
                "referenced_table": r.referenced_table,
                "referenced_column": r.referenced_column,
            }
            for r in relationships
        ],
        key=lambda x: (x["table_name"], x["column_name"]),
    )
    return json.dumps({"tables": table_part, "relationships": rel_part}, sort_keys=True)


def compute_content_hash(tables: list[TableInfo], relationships: list[ForeignKeyEdge]) -> str:
    payload = _canonical_payload(tables, relationships)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_graph(tables: list[TableInfo], relationships: list[ForeignKeyEdge]) -> dict[str, Any]:
    nodes = [{"id": t.name, "type": "table", "columns": t.columns} for t in tables]
    edges = [
        {
            "from": e.table_name,
            "to": e.referenced_table,
            "via": f"{e.table_name}.{e.column_name} -> {e.referenced_table}.{e.referenced_column}",
        }
        for e in relationships
    ]
    return {"nodes": nodes, "edges": edges}


def _format_schema_text(tables: list[TableInfo], relationships: list[ForeignKeyEdge]) -> str:
    lines: list[str] = []
    for table in tables:
        lines.append(f"Table: {table.name}")
        lines.append(f"Columns: {', '.join(table.columns)}\n")
    if relationships:
        lines.append("Relationships:")
        for fk in relationships:
            lines.append(
                f"{fk.table_name}.{fk.column_name} → {fk.referenced_table}.{fk.referenced_column}"
            )
    return "\n".join(lines).strip()


def capture_schema_snapshot() -> SchemaSnapshot:
    """Live read from INFORMATION_SCHEMA / SHOW TABLES (same source as agent schema)."""
    connection = None
    cursor = None
    tables: list[TableInfo] = []
    relationships: list[ForeignKeyEdge] = []

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SHOW TABLES")
        table_names = [list(row.values())[0] for row in cursor.fetchall()]

        for table in table_names:
            cursor.execute(f"DESCRIBE `{table}`")
            columns = [row["Field"] for row in cursor.fetchall()]
            tables.append(TableInfo(name=table, columns=columns))

        cursor.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE REFERENCED_TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            (config.DB_NAME,),
        )
        for row in cursor.fetchall():
            relationships.append(
                ForeignKeyEdge(
                    table_name=row["TABLE_NAME"],
                    column_name=row["COLUMN_NAME"],
                    referenced_table=row["REFERENCED_TABLE_NAME"],
                    referenced_column=row["REFERENCED_COLUMN_NAME"],
                )
            )

    except Error as exc:
        raise RuntimeError(f"Schema capture failed: {exc}") from exc
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    content_hash = compute_content_hash(tables, relationships)
    text = _format_schema_text(tables, relationships)
    graph = _build_graph(tables, relationships)
    return SchemaSnapshot(
        tables=tables,
        relationships=relationships,
        text=text,
        content_hash=content_hash,
        graph=graph,
    )
