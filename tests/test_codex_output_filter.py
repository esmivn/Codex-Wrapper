import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import codex


SAMPLE_OUTPUT = """[2025-09-18T23:14:43] OpenAI Codex v0.36.0 (research preview)
workdir: /home/user/codex-workspace
model: gpt-5
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, ] (network access enabled)
reasoning effort: high
reasoning summaries: detailed
[2025-09-18T23:14:43] User instructions:
Tell me the current weather.
Assistant:
 [2025-09-18T23:14:51] 🌐 Searched: weather: Kobe, Hyogo, Japan
[2025-09-18T23:15:14] codex

Current weather is cloudy, 24 C.

Let me know if you need hourly data.
[2025-09-18T23:15:15] tokens used: 12345
"""


EXPECTED_TEXT = "Current weather is cloudy, 24 C.\n\nLet me know if you need hourly data."


def test_sanitize_codex_text_removes_metadata():
    cleaned = codex._sanitize_codex_text(SAMPLE_OUTPUT)
    assert cleaned == EXPECTED_TEXT


def test_codex_output_filter_streaming():
    filt = codex._CodexOutputFilter()
    collected: list[str] = []
    for raw_line in SAMPLE_OUTPUT.splitlines(keepends=True):
        processed = filt.process(raw_line)
        if processed:
            collected.append(processed)
    assert "".join(collected).rstrip("\n") == EXPECTED_TEXT


def test_user_block_is_removed():
    filt = codex._CodexOutputFilter()
    lines = [
        "[2025-09-18T23:14:43] User instructions:\n",
        "今日の神戸の天気は？\n",
        "[2025-09-18T23:14:51] codex\n",
        "\n",
        "神戸の天気は快晴です。\n",
    ]
    out = [filt.process(line) for line in lines]
    rendered = "".join(part for part in out if part)
    assert rendered.strip() == "神戸の天気は快晴です。"


def test_partial_line_can_stream_after_assistant_marker():
    filt = codex._CodexOutputFilter()

    assert filt.process("Assistant:\n") is None
    assert filt.can_stream_partial("<p>Hello") is True


def test_run_codex_streams_partial_single_line_output(monkeypatch, tmp_path):
    monkeypatch.setattr(codex.settings, "codex_workdir", str(tmp_path), raising=False)
    monkeypatch.setattr(codex.settings, "timeout_seconds", 5, raising=False)
    monkeypatch.setattr(codex, "_WORKDIR_PATH", None, raising=False)
    monkeypatch.setattr(codex, "_WORKDIR_NEEDS_SKIP_GIT_CHECK", False, raising=False)
    monkeypatch.setattr(codex, "_build_cmd_and_env", lambda *_, **__: ["codex", "exec"])
    monkeypatch.setattr(codex, "_build_codex_env", lambda *_, **__: {})

    class FakeStdout:
        def __init__(self, chunks):
            self._chunks = list(chunks)

        async def read(self, _n):
            if self._chunks:
                return self._chunks.pop(0)
            return b""

    class FakeStderr:
        async def read(self):
            return b""

    class FakeProcess:
        def __init__(self):
            self.stdout = FakeStdout(
                [
                    b"Assistant:\n",
                    b"<p>Hello",
                    b" world",
                    b"</p>",
                ]
            )
            self.stderr = FakeStderr()
            self.returncode = 0

        async def wait(self):
            self.returncode = 0
            return 0

        def kill(self):
            self.returncode = 0

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProcess()

    monkeypatch.setattr(
        codex.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    async def _collect():
        parts = []
        async for chunk in codex.run_codex("prompt"):
            parts.append(chunk)
        return parts

    parts = asyncio.run(_collect())
    assert parts == ["<p>Hello", " world", "</p>", "\n"]


def test_build_codex_env_applies_runtime_overrides(monkeypatch, tmp_path):
    config_dir = tmp_path / ".codex-home"
    monkeypatch.setattr(codex.settings, "codex_config_dir", str(config_dir), raising=False)

    env = codex._build_codex_env(
        tmp_path,
        env_overrides={
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
            "OPENAI_API_KEY": "or-test-key",
        },
    )

    assert env["CODEX_HOME"] == str(config_dir)
    assert env["OPENAI_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert env["OPENAI_API_KEY"] == "or-test-key"


def test_build_cmd_and_env_leaves_model_provider_tables_unquoted(monkeypatch, tmp_path):
    monkeypatch.setattr(codex.settings, "codex_path", "codex", raising=False)
    monkeypatch.setattr(codex.settings, "sandbox_mode", "read-only", raising=False)
    monkeypatch.setattr(codex.settings, "hide_reasoning", False, raising=False)
    monkeypatch.setattr(codex.settings, "approval_policy", None, raising=False)
    monkeypatch.setattr(codex.settings, "reasoning_effort", "medium", raising=False)
    monkeypatch.setattr(codex, "_resolve_codex_executable", lambda: "codex")
    monkeypatch.setattr(codex, "_resolve_workdir_state", lambda *_args, **_kwargs: (tmp_path, True))

    cmd = codex._build_cmd_and_env(
        "prompt",
        overrides={
            "model_provider": "openrouter",
            "model_providers.openrouter": '{ name = "OpenRouter", base_url = "https://openrouter.ai/api/v1", env_key = "OPENROUTER_API_KEY", wire_api = "responses" }',
        },
        model="google/gemma-4-31b-it",
        workdir=tmp_path,
    )

    assert '--config' in cmd
    assert 'model_provider="openrouter"' in cmd
    assert 'model_providers.openrouter={ name = "OpenRouter", base_url = "https://openrouter.ai/api/v1", env_key = "OPENROUTER_API_KEY", wire_api = "responses" }' in cmd
