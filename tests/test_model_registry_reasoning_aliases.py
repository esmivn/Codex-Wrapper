from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import model_registry


def test_gpt51_models_expose_reasoning_aliases(monkeypatch):
    available = ["gpt-5.1", "o4-mini"]
    monkeypatch.setattr(model_registry, "_AVAILABLE_MODELS", available)
    merged = model_registry._merge_default_reasoning_aliases(
        available, {"o4-mini": ("low",)}
    )
    monkeypatch.setattr(model_registry, "_REASONING_ALIAS_MAP", merged)

    models = model_registry.get_available_models(include_reasoning_aliases=True)

    assert "gpt-5.1 low" in models
    assert "gpt-5.1 high" in models
    assert "gpt-5.1 xhigh" in models
    assert "o4-mini low" in models


def test_choose_model_accepts_gpt51_reasoning_suffix(monkeypatch):
    available = ["gpt-5.1"]
    monkeypatch.setattr(model_registry, "_AVAILABLE_MODELS", available)
    merged = model_registry._merge_default_reasoning_aliases(available, {})
    monkeypatch.setattr(model_registry, "_REASONING_ALIAS_MAP", merged)

    model, effort = model_registry.choose_model("gpt-5.1 low")

    assert model == "gpt-5.1"
    assert effort == "low"


def test_openrouter_models_are_listed_when_key_is_configured(monkeypatch):
    monkeypatch.setattr(model_registry, "_AVAILABLE_MODELS", ["gpt-5.1"])
    monkeypatch.setattr(
        model_registry.settings, "openrouter_api_key", "or-test-key", raising=False
    )
    monkeypatch.setattr(
        model_registry.settings,
        "openrouter_model",
        "openai/gpt-5.1",
        raising=False,
    )
    monkeypatch.setattr(
        model_registry, "_OPENROUTER_MODELS", ["openai/gpt-5.1", "google/gemini-2.5-pro"]
    )
    merged = model_registry._merge_default_reasoning_aliases(
        model_registry._combined_available_models(), {}
    )
    monkeypatch.setattr(model_registry, "_REASONING_ALIAS_MAP", merged)

    models = model_registry.get_available_models(include_reasoning_aliases=True)

    assert "openai/gpt-5.1" in models
    assert "google/gemini-2.5-pro" in models
    assert "openai/gpt-5.1 high" in models


def test_resolve_model_request_uses_openrouter_when_available(monkeypatch):
    monkeypatch.setattr(
        model_registry.settings, "openrouter_api_key", "or-test-key", raising=False
    )
    monkeypatch.setattr(
        model_registry.settings,
        "openrouter_base_url",
        "https://openrouter.ai/api/v1",
        raising=False,
    )
    monkeypatch.setattr(
        model_registry.settings,
        "openrouter_model",
        "openai/gpt-5.1",
        raising=False,
    )
    monkeypatch.setattr(
        model_registry.settings, "openrouter_reasoning_effort", "high", raising=False
    )
    monkeypatch.setattr(model_registry, "_AVAILABLE_MODELS", ["gpt-5.1"])
    monkeypatch.setattr(model_registry, "_OPENROUTER_MODELS", ["openai/gpt-5.1"])
    merged = model_registry._merge_default_reasoning_aliases(
        model_registry._combined_available_models(), {}
    )
    monkeypatch.setattr(model_registry, "_REASONING_ALIAS_MAP", merged)

    model, effort, env, provider_cfg, display = model_registry.resolve_model_request(None)

    assert model == "openai/gpt-5.1"
    assert effort == "high"
    assert env == {
        "OPENROUTER_API_KEY": "or-test-key",
    }
    assert provider_cfg == {
        "model_provider": "openrouter",
        "model_providers.openrouter": '{ name = "OpenRouter", base_url = "https://openrouter.ai/api/v1", env_key = "OPENROUTER_API_KEY", wire_api = "responses" }',
    }
    assert display == "openai/gpt-5.1 high"


def test_resolve_model_request_falls_back_without_openrouter_key(monkeypatch):
    monkeypatch.setattr(model_registry.settings, "openrouter_api_key", "", raising=False)
    monkeypatch.setattr(model_registry, "_AVAILABLE_MODELS", ["gpt-5.1"])
    monkeypatch.setattr(model_registry, "_OPENROUTER_MODELS", [])
    merged = model_registry._merge_default_reasoning_aliases(["gpt-5.1"], {})
    monkeypatch.setattr(model_registry, "_REASONING_ALIAS_MAP", merged)

    model, effort, env, provider_cfg, display = model_registry.resolve_model_request(None)

    assert model == "gpt-5.1"
    assert effort == "high"
    assert env is None
    assert provider_cfg is None
    assert display == "gpt-5.1 high"
