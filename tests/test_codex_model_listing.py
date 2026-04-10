import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import model_registry
from app.codex import CodexError


def test_initialize_model_registry_loads_models_from_current_sources(monkeypatch):
    monkeypatch.setattr(
        model_registry,
        "apply_codex_profile_overrides",
        lambda: None,
    )

    async def fake_list_codex_models():
        return ["gpt-5.1-codex", "o4-mini", "gpt-5"]

    monkeypatch.setattr(model_registry, "list_codex_models", fake_list_codex_models)
    monkeypatch.setattr(model_registry, "_load_openrouter_models", lambda: [])
    monkeypatch.setattr(
        model_registry,
        "builtin_reasoning_aliases",
        lambda: {"gpt-5.1-codex": ("low", "high")},
    )
    monkeypatch.setattr(model_registry, "_AVAILABLE_MODELS", ["codex-cli"])
    monkeypatch.setattr(model_registry, "_OPENROUTER_MODELS", [])
    monkeypatch.setattr(model_registry, "_REASONING_ALIAS_MAP", {})
    monkeypatch.setattr(model_registry, "_LAST_ERROR", None)

    models = asyncio.run(model_registry.initialize_model_registry())

    assert models == ["gpt-5.1-codex", "gpt-5.1", "o4-mini", "gpt-5"]
    assert model_registry.get_available_models(include_reasoning_aliases=True) == [
        "gpt-5.1-codex",
        "gpt-5.1",
        "o4-mini",
        "gpt-5",
        "gpt-5.1-codex low",
        "gpt-5.1-codex high",
        "gpt-5.1 low",
        "gpt-5.1 medium",
        "gpt-5.1 high",
        "gpt-5.1 xhigh",
        "gpt-5 low",
        "gpt-5 medium",
        "gpt-5 high",
        "gpt-5 xhigh",
    ]
    assert model_registry.get_last_error() is None


def test_initialize_model_registry_falls_back_when_discovery_fails(monkeypatch):
    monkeypatch.setattr(
        model_registry,
        "apply_codex_profile_overrides",
        lambda: None,
    )

    async def fake_list_codex_models():
        raise CodexError("boom")

    monkeypatch.setattr(model_registry, "list_codex_models", fake_list_codex_models)
    monkeypatch.setattr(model_registry, "_load_openrouter_models", lambda: [])
    monkeypatch.setattr(model_registry, "_AVAILABLE_MODELS", ["codex-cli"])
    monkeypatch.setattr(model_registry, "_OPENROUTER_MODELS", [])
    monkeypatch.setattr(model_registry, "_REASONING_ALIAS_MAP", {})
    monkeypatch.setattr(model_registry, "_LAST_ERROR", None)

    models = asyncio.run(model_registry.initialize_model_registry())

    assert models == ["codex-cli", "gpt-5.1", "gpt-5"]
    assert model_registry.get_default_model() == "gpt-5.1"
    assert model_registry.get_last_error() == "boom"
