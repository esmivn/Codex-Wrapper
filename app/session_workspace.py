import json
import os
import re
import stat
from base64 import b64decode
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .config import settings


DEFAULT_USER_ID = settings.codex_default_user_id
_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_UPLOAD_NAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class SessionWorkspace:
    user_id: str
    chat_id: str
    workspace_root: Path
    user_dir: Path
    session_dir: Path

    @property
    def metadata_dir(self) -> Path:
        return self.session_dir / ".codex-wrapper"

    @property
    def history_path(self) -> Path:
        return self.metadata_dir / "messages.json"


def _validate_segment(value: str, *, field_name: str) -> str:
    candidate = (value or "").strip()
    if not _SEGMENT_PATTERN.fullmatch(candidate):
        raise ValueError(
            f"Invalid {field_name}. Use 1-64 chars from letters, numbers, dot, underscore, or hyphen."
        )
    return candidate


def get_workspace_root() -> Path:
    return Path(settings.codex_workdir).expanduser()


def get_user_workspace_root(user_id: Optional[str] = None) -> Path:
    resolved_user_id = _validate_segment(user_id or DEFAULT_USER_ID, field_name="user_id")
    workspace_root = get_workspace_root()
    if workspace_root.name == DEFAULT_USER_ID:
        if resolved_user_id == DEFAULT_USER_ID:
            return workspace_root
        return workspace_root.parent / resolved_user_id
    return workspace_root / resolved_user_id


def get_session_workspace(chat_id: str, user_id: Optional[str] = None) -> SessionWorkspace:
    resolved_user_id = _validate_segment(user_id or DEFAULT_USER_ID, field_name="user_id")
    resolved_chat_id = _validate_segment(chat_id, field_name="chat_id")

    workspace_root = get_workspace_root()
    user_dir = get_user_workspace_root(resolved_user_id)
    session_dir = user_dir / resolved_chat_id

    return SessionWorkspace(
        user_id=resolved_user_id,
        chat_id=resolved_chat_id,
        workspace_root=workspace_root,
        user_dir=user_dir,
        session_dir=session_dir,
    )


def ensure_session_workspace(chat_id: str, user_id: Optional[str] = None) -> SessionWorkspace:
    session = get_session_workspace(chat_id=chat_id, user_id=user_id)
    session.session_dir.mkdir(parents=True, exist_ok=True)
    return session


def _sanitize_upload_name(filename: str) -> str:
    candidate = Path((filename or "").strip()).name.strip()
    if not candidate or candidate in {".", ".."}:
        raise ValueError("Uploaded file name is required.")
    if candidate.startswith("."):
        candidate = candidate.lstrip(".")
    candidate = _UPLOAD_NAME_PATTERN.sub("-", candidate)
    candidate = candidate.strip("-.")
    if not candidate:
        raise ValueError("Uploaded file name is invalid.")
    return candidate[:120]


def _dedupe_upload_path(session_dir: Path, filename: str) -> Path:
    target = session_dir / filename
    if not target.exists():
        return target
    stem = target.stem or "file"
    suffix = target.suffix
    for index in range(2, 1000):
        candidate = session_dir / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError("Unable to allocate a unique file name for upload.")


def resolve_session_file_path(
    user_id: str,
    chat_id: str,
    relative_path: str,
) -> Path:
    session = ensure_session_workspace(chat_id=chat_id, user_id=user_id)
    candidate = (session.session_dir / relative_path).resolve()
    session_root = session.session_dir.resolve()
    if candidate != session_root and session_root not in candidate.parents:
        raise ValueError("Requested file path escapes the session workspace.")
    return candidate


def load_session_messages(chat_id: str, user_id: Optional[str] = None) -> list[dict[str, Any]]:
    session = ensure_session_workspace(chat_id=chat_id, user_id=user_id)
    if not session.history_path.is_file():
        return []
    try:
        payload = json.loads(session.history_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    messages: list[dict[str, Any]] = []
    for entry in payload:
        if isinstance(entry, dict) and "role" in entry and "content" in entry:
            message = {"role": entry["role"], "content": entry["content"]}
            if isinstance(entry.get("model"), str) and entry["model"].strip():
                message["model"] = entry["model"].strip()
            messages.append(message)
    return messages


def save_session_messages(
    chat_id: str,
    messages: list[dict[str, Any]],
    user_id: Optional[str] = None,
) -> SessionWorkspace:
    session = ensure_session_workspace(chat_id=chat_id, user_id=user_id)
    session.metadata_dir.mkdir(parents=True, exist_ok=True)
    session.history_path.write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return session


def save_uploaded_file(
    chat_id: str,
    *,
    filename: str,
    content_base64: str,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    session = ensure_session_workspace(chat_id=chat_id, user_id=user_id)
    safe_name = _sanitize_upload_name(filename)
    try:
        payload = b64decode(content_base64.encode("utf-8"), validate=True)
    except Exception as exc:
        raise ValueError(f"Invalid base64 payload for file '{filename}'.") from exc

    target = _dedupe_upload_path(session.session_dir, safe_name)
    target.write_bytes(payload)
    stat_result = target.stat()
    return {
        "name": target.name,
        "relative_path": target.name,
        "size": stat_result.st_size,
        "modified_at": datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat(),
    }


def delete_session_workspace(chat_id: str, user_id: Optional[str] = None) -> SessionWorkspace:
    session = get_session_workspace(chat_id=chat_id, user_id=user_id)
    if not session.session_dir.is_dir():
        raise FileNotFoundError(f"Session '{session.chat_id}' does not exist.")
    _remove_tree(session.session_dir)
    return session


def _remove_tree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        _unlink_path(path)
        return
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            _remove_tree(child)
        else:
            _unlink_path(child)
    _rmdir_path(path)


def _unlink_path(path: Path) -> None:
    try:
        path.unlink()
    except PermissionError:
        current_mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(current_mode | stat.S_IWUSR)
        path.unlink()


def _rmdir_path(path: Path) -> None:
    try:
        path.rmdir()
    except PermissionError:
        current_mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(current_mode | stat.S_IWUSR | stat.S_IXUSR)
        os.chmod(path.parent, stat.S_IMODE(path.parent.stat().st_mode) | stat.S_IWUSR | stat.S_IXUSR)
        path.rmdir()


def list_recent_sessions(
    *,
    user_id: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    resolved_user_id = _validate_segment(user_id or DEFAULT_USER_ID, field_name="user_id")
    user_dir = get_user_workspace_root(resolved_user_id)
    if not user_dir.is_dir():
        return []

    entries: list[dict[str, Any]] = []
    for child in user_dir.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            session = get_session_workspace(chat_id=child.name, user_id=resolved_user_id)
        except ValueError:
            continue

        history_path = session.history_path
        messages = load_session_messages(chat_id=session.chat_id, user_id=session.user_id)
        title = _summarize_session_title(messages, fallback=session.chat_id)
        last_message = messages[-1]["content"] if messages else ""
        preview = str(last_message).strip().replace("\n", " ")
        if len(preview) > 120:
            preview = preview[:117] + "..."
        try:
            timestamp = history_path.stat().st_mtime if history_path.exists() else child.stat().st_mtime
        except Exception:
            timestamp = 0.0

        entries.append(
            {
                "user_id": session.user_id,
                "chat_id": session.chat_id,
                "title": title,
                "workdir": str(session.session_dir),
                "public_base_url": f"/workspace/{session.user_id}/{session.chat_id}/",
                "message_count": len(messages),
                "preview": preview,
                "updated_at": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
                "_timestamp": timestamp,
            }
        )

    entries.sort(key=lambda item: item["_timestamp"], reverse=True)
    trimmed = entries[: max(1, limit)]
    for item in trimmed:
        item.pop("_timestamp", None)
    return trimmed


def _summarize_session_title(messages: list[dict[str, Any]], *, fallback: str) -> str:
    for message in messages:
        if str(message.get("role", "")).lower() != "user":
            continue
        text = str(message.get("content", "")).strip()
        normalized = " ".join(text.split())
        if not normalized:
            continue
        words = normalized.split(" ")
        if len(words) > 8:
            return " ".join(words[:8]) + "..."
        if len(normalized) > 60:
            return normalized[:57] + "..."
        return normalized
    return fallback


def list_session_files(
    chat_id: str,
    *,
    user_id: Optional[str] = None,
    limit: int = 40,
) -> list[dict[str, Any]]:
    session = get_session_workspace(chat_id=chat_id, user_id=user_id)
    if not session.session_dir.is_dir():
        return []

    files: list[dict[str, Any]] = []
    for child in session.session_dir.rglob("*"):
        if not child.is_file():
            continue
        relative = child.relative_to(session.session_dir)
        if any(part.startswith(".") for part in relative.parts):
            continue
        stat_result = child.stat()
        files.append(
            {
                "name": child.name,
                "relative_path": relative.as_posix(),
                "size": stat_result.st_size,
                "modified_at": datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    files.sort(key=lambda item: item["modified_at"], reverse=True)
    return files[: max(1, limit)]
