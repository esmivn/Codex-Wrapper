import json
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .config import settings


DEFAULT_USER_ID = "default"
_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


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


def ensure_session_workspace(chat_id: str, user_id: Optional[str] = None) -> SessionWorkspace:
    resolved_user_id = _validate_segment(user_id or DEFAULT_USER_ID, field_name="user_id")
    resolved_chat_id = _validate_segment(chat_id, field_name="chat_id")

    workspace_root = get_workspace_root()
    user_dir = workspace_root / resolved_user_id
    session_dir = user_dir / resolved_chat_id
    session_dir.mkdir(parents=True, exist_ok=True)

    return SessionWorkspace(
        user_id=resolved_user_id,
        chat_id=resolved_chat_id,
        workspace_root=workspace_root,
        user_dir=user_dir,
        session_dir=session_dir,
    )


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
            messages.append({"role": entry["role"], "content": entry["content"]})
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


def list_recent_sessions(
    *,
    user_id: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    resolved_user_id = _validate_segment(user_id or DEFAULT_USER_ID, field_name="user_id")
    workspace_root = get_workspace_root()
    user_dir = workspace_root / resolved_user_id
    if not user_dir.is_dir():
        return []

    entries: list[dict[str, Any]] = []
    for child in user_dir.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        try:
            session = ensure_session_workspace(chat_id=child.name, user_id=resolved_user_id)
        except ValueError:
            continue

        history_path = session.history_path
        messages = load_session_messages(chat_id=session.chat_id, user_id=session.user_id)
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
