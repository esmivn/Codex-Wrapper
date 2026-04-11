from pathlib import Path
from typing import List, Dict, Any, Tuple

from .config import settings


_DEFAULT_PROFILE_DIR = Path(__file__).resolve().parent.parent / "workspace" / "codex_profile"
_DEFAULT_WRAPPER_SYSTEM_PROMPT = """Wrapper execution rules:
- Treat the current working directory as the primary workspace for this request.
- Create user-facing files inside the current working directory unless the user explicitly asks otherwise.
- Always format the final assistant response as an HTML fragment that can be rendered directly in a browser chat interface.
- Do not wrap the response in Markdown fences.
- Use normal HTML elements for rich output such as <img>, <audio>, <video>, <canvas>, <svg>, <a>, <button>, and inline <script> when needed.
- Keep the fragment self-contained with inline CSS/JS unless the user explicitly asks for separate files.
- If you create a browser-viewable artifact such as HTML, return its final HTTP link inside the HTML fragment when one is available.
- Prefer sharing the public URL instead of an inaccessible local filesystem path when the user needs to open a file.
- Keep generated files organized inside the session workspace and avoid writing outside it unless required.
- Reusable user-created skills must follow the standard `SKILL.md` layout.
- Shared system skills are read-only and must not be modified.
- If a plain text answer would normally be enough, wrap it in simple HTML such as <p>...</p>.
- When you mention a generated file, prefer a clickable <a href="...">...</a> link.
- Do not add target attributes, window.open calls, or inline click handlers to links; the frontend controls how links open."""


def _content_to_text(content: Any) -> str:
    """Best-effort conversion of message `content` into plain text.

    Supported variants:
    - str → as-is
    - list of {type:"text"|"input_text", text} → join text fields
    - list of str → join
    - any other → stringified
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Typed parts (OpenAI-style content parts)
        parts: List[str] = []
        for p in content:
            if isinstance(p, dict):
                t = p.get("type")
                if t in ("text", "input_text") and isinstance(p.get("text"), str):
                    parts.append(p["text"])
                # Ignore non-text parts (images, tool calls, etc.)
            elif isinstance(p, str):
                parts.append(p)
        if parts:
            return "".join(parts)
    # Fallback: stringify
    try:
        return str(content)
    except Exception:
        return ""


def _extract_images(content: Any) -> List[str]:
    """Extract image URLs from a message `content` structure."""
    images: List[str] = []
    if isinstance(content, list):
        for p in content:
            if isinstance(p, dict):
                t = p.get("type")
                if t in ("image_url", "input_image", "image"):
                    url_obj = p.get("image_url") or p.get("url")
                    if isinstance(url_obj, dict):
                        url = url_obj.get("url")
                    else:
                        url = url_obj
                    if isinstance(url, str):
                        images.append(url)
    return images


def load_wrapper_system_prompt_parts() -> List[str]:
    """Return server-managed system prompt parts that should apply to every request."""

    parts: List[str] = [_DEFAULT_WRAPPER_SYSTEM_PROMPT]

    configured_file = settings.codex_system_prompt_file
    if configured_file:
        candidate = Path(configured_file).expanduser()
    else:
        profile_dir = (
            Path(settings.codex_profile_dir).expanduser()
            if settings.codex_profile_dir
            else _DEFAULT_PROFILE_DIR
        )
        candidate = profile_dir / "system_prompt.md"

    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8").strip()
        if text:
            parts.append(text)

    inline_prompt = (settings.codex_system_prompt or "").strip()
    if inline_prompt:
        parts.append(inline_prompt)

    return parts


def build_prompt_and_images(
    messages: List[Dict[str, Any]],
    injected_system_parts: List[str] | None = None,
) -> Tuple[str, List[str]]:
    """Convert chat messages into a prompt string and collect image URLs."""
    system_parts: List[str] = [part.strip() for part in (injected_system_parts or []) if part and part.strip()]
    convo: List[Dict[str, Any]] = []
    images: List[str] = []

    for m in messages:
        role = (m.get("role") or "").strip().lower()
        # Treat 'developer' as 'system' for compatibility
        normalized_role = "system" if role == "developer" else role
        content = m.get("content")
        images.extend(_extract_images(content))
        text = _content_to_text(content)
        if normalized_role == "system":
            if text:
                system_parts.append(text.strip())
        else:
            convo.append({"role": normalized_role or "user", "content": text})

    lines: List[str] = []
    if system_parts:
        lines.append("\n".join(system_parts))
        lines.append("")

    for msg in convo:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content'].strip()}")

    lines.append("Assistant:")
    return "\n".join(lines), images


def normalize_responses_input(inp: Any) -> List[Dict[str, Any]]:
    """Normalize Responses API `input` into OpenAI chat `messages`.

    Supported variants (minimal):
    - str → single user message
    - list of content parts (`input_text`/`input_image`/...) → single user message
    - list of {role, content} (chat-like) → pass through
    - list of str → concatenate
    """
    if isinstance(inp, str):
        return [{"role": "user", "content": inp}]

    if isinstance(inp, list):
        # list of dict with type field (content parts)
        if inp and isinstance(inp[0], dict) and "type" in inp[0] and "role" not in inp[0]:
            return [{"role": "user", "content": inp}]

        # list of dict with role/content (chat-like)
        if all(isinstance(x, dict) and "role" in x and "content" in x for x in inp):
            msgs: List[Dict[str, Any]] = []
            for x in inp:
                msgs.append({"role": str(x.get("role")), "content": x.get("content")})
            return msgs

        # list of str → concatenate
        if all(isinstance(x, str) for x in inp):
            return [{"role": "user", "content": "".join(inp)}]

    raise ValueError("Unsupported input format for Responses API")
