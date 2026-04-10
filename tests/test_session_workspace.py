import json
import os
from base64 import b64encode

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


def test_ensure_session_workspace_avoids_duplicate_default_segment(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path / "default"), raising=False
    )

    session = session_workspace.ensure_session_workspace("chat-rooted-default")

    assert session.user_id == "default"
    assert session.session_dir == tmp_path / "default" / "chat-rooted-default"
    assert session.session_dir.is_dir()


def test_non_default_user_stays_as_sibling_when_workdir_is_default_user_root(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path / "default"), raising=False
    )

    session = session_workspace.ensure_session_workspace("chat-bob", user_id="bob")

    assert session.user_id == "bob"
    assert session.session_dir == tmp_path / "bob" / "chat-bob"
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
        {"role": "assistant", "content": "world", "model": "gpt-5.1 high"},
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
    assert items[0]["title"] == "chat-new"
    assert items[0]["preview"] == "newer message"


def test_delete_session_workspace_removes_chat_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path), raising=False
    )

    session = session_workspace.save_session_messages(
        "chat-delete-me",
        [{"role": "assistant", "content": "bye"}],
    )
    sample_file = session.session_dir / "artifact.txt"
    sample_file.write_text("cleanup", encoding="utf-8")
    sample_file.chmod(0o400)

    deleted = session_workspace.delete_session_workspace("chat-delete-me")

    assert deleted.chat_id == "chat-delete-me"
    assert not session.session_dir.exists()


def test_save_uploaded_file_uses_session_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path), raising=False
    )

    payload = b64encode(b"hello upload").decode("utf-8")
    saved = session_workspace.save_uploaded_file(
        "chat-upload",
        filename="demo file.txt",
        content_base64=payload,
    )

    target = tmp_path / "default" / "chat-upload" / saved["relative_path"]
    assert target.read_bytes() == b"hello upload"
    assert saved["name"].startswith("demo-file")


def test_list_session_files_ignores_hidden_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path), raising=False
    )

    session = session_workspace.ensure_session_workspace("chat-files")
    (session.session_dir / "visible.txt").write_text("ok", encoding="utf-8")
    hidden_dir = session.session_dir / ".codex-wrapper"
    hidden_dir.mkdir(parents=True, exist_ok=True)
    (hidden_dir / "messages.json").write_text("[]", encoding="utf-8")

    files = session_workspace.list_session_files("chat-files")

    assert [item["relative_path"] for item in files] == ["visible.txt"]


def test_list_recent_sessions_title_uses_first_user_message(monkeypatch, tmp_path):
    monkeypatch.setattr(
        session_workspace.settings, "codex_workdir", str(tmp_path), raising=False
    )

    session_workspace.save_session_messages(
        "chat-title",
        [
            {"role": "assistant", "content": "intro"},
            {"role": "user", "content": "Please review the quarterly retention dashboard and summarize risks"},
            {"role": "assistant", "content": "done"},
        ],
    )

    items = session_workspace.list_recent_sessions(limit=10)

    assert items[0]["chat_id"] == "chat-title"
    assert items[0]["title"] == "Please review the quarterly retention dashboard and summarize..."
