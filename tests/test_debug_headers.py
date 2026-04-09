from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.main import _debug_headers


def test_debug_headers_for_direct_model_selection():
    headers = _debug_headers(
        requested_model="qwen/qwen3.6-plus",
        resolved_model="qwen/qwen3.6-plus",
        resolved_label="qwen/qwen3.6-plus",
        provider_config={"model_provider": "openrouter"},
    )

    assert headers["X-Codex-Requested-Model"] == "qwen/qwen3.6-plus"
    assert headers["X-Codex-Resolved-Model"] == "qwen/qwen3.6-plus"
    assert headers["X-Codex-Resolved-Label"] == "qwen/qwen3.6-plus"
    assert headers["X-Codex-Resolved-Provider"] == "openrouter"
    assert headers["X-Codex-Fallback-Applied"] == "false"


def test_debug_headers_mark_fallback():
    headers = _debug_headers(
        requested_model="openai/gpt-5.1",
        resolved_model="gpt-5.1",
        resolved_label="gpt-5.1 high",
        provider_config=None,
    )

    assert headers["X-Codex-Requested-Model"] == "openai/gpt-5.1"
    assert headers["X-Codex-Resolved-Model"] == "gpt-5.1"
    assert headers["X-Codex-Resolved-Label"] == "gpt-5.1 high"
    assert headers["X-Codex-Resolved-Provider"] == "codex-default"
    assert headers["X-Codex-Fallback-Applied"] == "true"
