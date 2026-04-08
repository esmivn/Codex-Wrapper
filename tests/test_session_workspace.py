import json
import os

import pytest

from app import session_workspace


def test_ensure_session_workspace_uses_default_user(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path), raising=False
    )

    session = session_workspace.ensure_session_workspace("chat-abc123")

    assert session.user_id == "default"
    assert session.chat_id == "chat-abc123"
    assert session.session_dir == tmp_path / "default" / "chat-abc123"
    assert session.session_dir.is_dir()


def test_resolve_session_file_path_blocks_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path), raising=False
    )

    with pytest.raises(ValueError):
        session_workspace.resolve_session_file_path(
            user_id="default",
            chat_id="chat-abc123",
            relative_path="../escape.txt",
        )


def test_save_and_load_session_messages(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path), raising=False
    )

    payload = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]
    session = session_workspace.save_session_messages("chat-abc123", payload)

    assert session.history_path.is_file()
    on_disk = json.loads(session.history_path.read_text(encoding="utf-8"))
    assert on_disk == payload
    assert session_workspace.load_session_messages("chat-abc123") == payload


def test_list_recent_sessions_sorts_by_latest_update(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path), raising=False
    )

    first = session_workspace.save_session_messages(
        "chat-old",
        [{"role": "assistant", "content": "older message"}],
    )
    second = session_workspace.save_session_messages(
        "chat-new",
        [{"role": "assistant", "content": "newer message"}],
    )

    first.history_path.touch()
    second.history_path.touch()
    first.history_path.chmod(0o644)
    second.history_path.chmod(0o644)

    os.utime(first.history_path, (1, 1))
    os.utime(second.history_path, (2, 2))

    items = session_workspace.list_recent_sessions(limit=10)

    assert [item["chat_id"] for item in items[:2]] == ["chat-new", "chat-old"]
    assert items[0]["preview"] == "newer message"
