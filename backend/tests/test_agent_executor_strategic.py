import app.agent_executor as agent_executor


def test_strategic_mode_response_structure(monkeypatch):
    def fake_execute_safe_sql(sql: str):
        if "low stock" in sql.lower():
            return {"success": False, "error": "table missing", "error_type": "SQL_ERROR", "sql": sql}
        return {"success": True, "results": [{"metric": 1}], "row_count": 1, "sql": sql}

    monkeypatch.setattr(agent_executor, "_execute_safe_sql", fake_execute_safe_sql)
    out = agent_executor._strategic_mode_response()
    assert out["status"] == "success"
    assert out["is_multi"] is True
    assert len(out["sub_responses"]) == 3
    assert "Result:" in out["explanation"]
