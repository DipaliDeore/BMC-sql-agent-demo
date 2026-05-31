"""Tests for schema snapshot hashing and graph building."""

from app.schema_snapshot import (
    ForeignKeyEdge,
    TableInfo,
    compute_content_hash,
    _build_graph,
    _format_schema_text,
)


def test_compute_content_hash_stable_for_same_schema():
    tables = [
        TableInfo(name="orders", columns=["id", "amount"]),
        TableInfo(name="users", columns=["id", "name"]),
    ]
    rels = [
        ForeignKeyEdge("orders", "user_id", "users", "id"),
    ]
    h1 = compute_content_hash(tables, rels)
    h2 = compute_content_hash(list(tables), list(rels))
    assert h1 == h2
    assert len(h1) == 64


def test_compute_content_hash_changes_when_column_order_differs():
    t1 = [TableInfo(name="t", columns=["a", "b"])]
    t2 = [TableInfo(name="t", columns=["b", "a"])]
    assert compute_content_hash(t1, []) == compute_content_hash(t2, [])


def test_build_graph_nodes_and_edges():
    tables = [TableInfo(name="a", columns=["x"])]
    rels = [ForeignKeyEdge("a", "x", "b", "y")]
    graph = _build_graph(tables, rels)
    assert len(graph["nodes"]) == 1
    assert graph["edges"][0]["from"] == "a"
    assert graph["edges"][0]["to"] == "b"


def test_format_schema_text_includes_relationships():
    tables = [TableInfo(name="t", columns=["c1"])]
    rels = [ForeignKeyEdge("t", "c1", "other", "id")]
    text = _format_schema_text(tables, rels)
    assert "Table: t" in text
    assert "Relationships:" in text
    assert "other.id" in text
