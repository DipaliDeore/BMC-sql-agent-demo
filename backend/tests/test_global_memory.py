"""Tests for cross-chat global memory."""

from unittest.mock import MagicMock, patch

from app.global_memory import (
    chat_needs_global_merge,
    get_global_memory,
    inject_global_memory,
    merge_chat_into_global_memory,
    merge_pending_chats,
    update_global_memory,
)


def test_get_and_update_global_memory_in_memory_fallback(monkeypatch):
    monkeypatch.setattr("app.global_memory.get_postgres_pool", lambda: None)
    update_global_memory("prefers concise answers")
    assert get_global_memory() == "prefers concise answers"
    update_global_memory("updated summary")
    assert get_global_memory() == "updated summary"


def test_inject_global_memory_empty_when_disabled(monkeypatch):
    monkeypatch.setattr("app.global_memory.config.GLOBAL_MEMORY_ENABLED", False)
    assert inject_global_memory() == ""


def test_inject_global_memory_includes_summary(monkeypatch):
    monkeypatch.setattr("app.global_memory.get_postgres_pool", lambda: None)
    monkeypatch.setattr("app.global_memory.config.GLOBAL_MEMORY_ENABLED", True)
    update_global_memory("* Often asks about sales.")
    block = inject_global_memory()
    assert "GLOBAL LONG-TERM MEMORY" in block
    assert "sales" in block


def test_merge_skips_empty_chat(monkeypatch):
    monkeypatch.setattr("app.global_memory.config.GLOBAL_MEMORY_ENABLED", True)
    with patch("app.global_memory.chat_store.get_chat", return_value={"id": "c1"}):
        with patch("app.global_memory.chat_store.list_messages", return_value=[]):
            out = merge_chat_into_global_memory("c1")
    assert out["updated"] is False


def test_merge_updates_summary(monkeypatch):
    monkeypatch.setattr("app.global_memory.get_postgres_pool", lambda: None)
    monkeypatch.setattr("app.global_memory.config.GLOBAL_MEMORY_ENABLED", True)
    update_global_memory("old memory")

    with (
        patch("app.global_memory.chat_store.get_chat", return_value={"id": "c1"}),
        patch(
            "app.global_memory.chat_store.list_messages",
            return_value=[
                {"role": "user", "content": "sales by month", "payload": None},
                {
                    "role": "assistant",
                    "content": "Here is the chart",
                    "payload": {"sql": "SELECT 1"},
                },
            ],
        ),
        patch(
            "app.global_memory.generate_global_memory_summary",
            return_value="* Likes sales trends.",
        ),
    ):
        out = merge_chat_into_global_memory("c1")

    assert out["updated"] is True
    assert get_global_memory() == "* Likes sales trends."


def test_get_global_memory_uses_dict_row_not_tuple_index(monkeypatch):
    """Pool connections use dict_row; row[0] raised KeyError(0) shown as '0' in UI."""
    row = {"memory_summary": "User likes sales questions."}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            pass

        def fetchone(self):
            return row

    class FakeConn:
        def cursor(self, row_factory=None):
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class FakePool:
        def connection(self):
            return FakeConn()

    monkeypatch.setattr("app.global_memory.config.GLOBAL_MEMORY_ENABLED", True)
    monkeypatch.setattr("app.global_memory.get_postgres_pool", lambda: FakePool())
    assert get_global_memory() == "User likes sales questions."


def test_merge_skips_already_merged_at_same_revision(monkeypatch):
    monkeypatch.setattr("app.global_memory.get_postgres_pool", lambda: None)
    monkeypatch.setattr("app.global_memory.config.GLOBAL_MEMORY_ENABLED", True)
    chat = {"id": "c1", "updated_at": "2026-01-01T00:00:00+00:00"}

    with (
        patch("app.global_memory.chat_store.get_chat", return_value=chat),
        patch(
            "app.global_memory.chat_store.list_messages",
            return_value=[{"role": "user", "content": "hi", "payload": None}],
        ),
        patch("app.global_memory.generate_global_memory_summary") as gen,
    ):
        gen.return_value = "memory v1"
        r1 = merge_chat_into_global_memory("c1")
        assert r1["updated"] is True
        gen.assert_called_once()
        r2 = merge_chat_into_global_memory("c1")
        assert r2["updated"] is False
        assert r2["message"] == "already merged"


def test_merge_pending_excludes_active_chat(monkeypatch):
    monkeypatch.setattr("app.global_memory.config.GLOBAL_MEMORY_ENABLED", True)
    chats = [
        {"id": "old", "updated_at": "2026-01-01T00:00:00+00:00"},
        {"id": "active", "updated_at": "2026-01-02T00:00:00+00:00"},
    ]

    with (
        patch("app.global_memory.chat_store.list_chats", return_value=chats),
        patch("app.global_memory.chat_needs_global_merge", side_effect=lambda cid: cid == "old"),
        patch("app.global_memory.merge_chat_into_global_memory") as merge_one,
    ):
        merge_one.return_value = {"ok": True, "updated": True}
        out = merge_pending_chats(exclude_chat_id="active")
        assert out["merged_chats"] == 1
        merge_one.assert_called_once_with("old")
