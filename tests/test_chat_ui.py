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
    assert 'id="theme-toggle"' in html
    assert "Dark Mode" in html
    assert "hidden-control" in html
    assert 'id="model-search"' in html
    assert "搜索模型" in html
    assert 'id="upload-trigger"' in html
    assert 'id="file-input"' in html
    assert 'id="session-files"' in html
    assert "上传文件" in html
    assert "uploadFiles(fileInput.files)" in html
    assert "content_base64" in html
    assert "renderSessionFiles(payload.files || [])" in html
    assert 'id="skill-menu"' in html
    assert '输入 <code>/</code> 可列出当前可用 skills' in html
    assert 'fetch("/v1/skills"' in html
    assert "skillMenuEl" in html
    assert "loadSkills" in html
    assert "refreshSkillMenu" in html
    assert "applySkillSelection" in html
    assert 'promptInput.value = `$${skill.name} `;' in html
    assert 'skillScopeLabel' in html
    assert 'skill-menu' in html
    assert "Enter 发送，Shift + Enter 换行" in html
    assert "grid-template-columns: 300px minmax(0, 1fr) 280px;" in html
    assert "chat_id" in html
    assert "/v1/chat/sessions/" in html
    assert "最近会话" in html
    assert "sidebar-right" in html
    assert 'fetch("/v1/chat/sessions?limit=6"' in html
    assert "payload.default_model" in html
    assert "populateModelOptions" in html
    assert "rememberedModelSelection" in html
    assert "codex-wrapper.chat.theme" in html
    assert "applyTheme" in html
    assert "refreshRenderedAssistantMessages" in html
    assert "messageState = new WeakMap()" in html
    assert 'document.body.dataset.theme = currentTheme;' in html
    assert 'themeToggleButton.textContent = currentTheme === "dark" ? "Light Mode" : "Dark Mode";' in html
    assert "refreshRenderedAssistantMessages();" in html
    assert 'body[data-theme="dark"] .hero' in html
    assert 'body[data-theme="dark"] .recent-item' in html
    assert 'body[data-theme="dark"] .recent-delete' in html
    assert 'if (modelSelect.value) {' in html
    assert "X-Codex-Resolved-Label" in html
    assert 'ASSISTANT (${normalizedModel})' in html
    assert "updateRoleLabel" in html
    assert "message.model ? { model: message.model } : {}" in html
    assert 'conversation.push({ role: "assistant", content, model: resolvedModelLabel });' in html
    assert "allModelIds.filter((modelId) => modelId.toLowerCase().includes(search))" in html
    assert 'modelSelect.value = "gpt-5.1 high"' in html
    assert "recent-item" in html
    assert "recent-item-link" in html
    assert "recent-delete" in html
    assert 'title.textContent = (item.title || item.chat_id || "").trim();' in html
    assert 'meta.textContent = [item.chat_id, count, updated].filter(Boolean).join(" · ");' in html
    assert "确认删除会话" in html
    assert 'method: "DELETE"' in html
    assert "deleteSession(item.chat_id, deleteButton)" in html
    assert "当前会话已删除，已切换到新对话" in html
    assert "recent-item-preview" not in html
    assert "allow-scripts allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox" in html
    assert 'type: "codex-wrapper-preview-height"' in html
    assert 'type: "codex-wrapper-open-popup"' in html
    assert 'window.open(new URL(url, window.location.href).href, popupWindowName, popupWindowFeatures)' in html
    assert 'const isDarkTheme = currentTheme === "dark";' in html
    assert 'color-scheme: ${isDarkTheme ? "dark" : "light"};' in html
    assert 'background: transparent;' in html
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
    assert 'sessionFilesEl.addEventListener("click"' in html
