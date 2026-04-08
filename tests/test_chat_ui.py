from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import chat_ui, static_asset


async def test_chat_ui_route_returns_html_file():
    response = await chat_ui()

    assert response.status_code == 200
    assert response.path.endswith("app/static/chat.html")
    assert response.media_type == "text/html"


async def test_static_asset_route_returns_typing_gif():
    response = await static_asset("typing-animation.gif")

    assert response.status_code == 200
    assert response.path.endswith("app/static/typing-animation.gif")
    assert response.media_type == "image/gif"


def test_chat_ui_static_html_includes_new_chat_controls():
    html = Path("app/static/chat.html").read_text(encoding="utf-8")

    assert "新对话" in html
    assert "sidebar-primary-action" in html
    assert "hidden-control" in html
    assert "Enter 发送，Shift + Enter 换行" in html
    assert "grid-template-columns: 300px minmax(0, 1fr) 280px;" in html
    assert "chat_id" in html
    assert "/v1/chat/sessions/" in html
    assert "最近会话" in html
    assert "sidebar-right" in html
    assert 'fetch("/v1/chat/sessions?limit=10"' in html
    assert "recent-item" in html
    assert "recent-item-preview" not in html
    assert "allow-scripts allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox" in html
    assert 'type: "codex-wrapper-preview-height"' in html
    assert 'type: "codex-wrapper-open-popup"' in html
    assert 'window.open(new URL(url, window.location.href).href, popupWindowName, popupWindowFeatures)' in html
    assert "streaming-caret" in html
    assert "流式输出中..." in html
    assert "assistant-waiting" in html
    assert '/static/typing-animation.gif' in html
    assert ".assistant-loading" in html
    assert 'articleEl.className = isPending ? "assistant-loading" : "message assistant"' in html
    assert 'pendingBare: true' in html
    assert 'wrapper.appendChild(body);' in html
    assert 'if (role === "assistant" && !isAssistantPending && !extraClass.includes("error")) {' in html
    assert "attachResizeHandles" in html
    assert "resize-handle" in html
    assert 'for (const direction of ["e", "s", "se"])' in html
    assert "syncPreviewFrameSize" in html
    assert "assistantPreviewAvailableHeight" in html
    assert 'body.className = "message-content"' in html
