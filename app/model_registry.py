"""Utility helpers for discovering and caching Codex/OpenRouter-proxy models."""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple
from urllib import error, request

from .codex import (
    CodexError,
    apply_codex_profile_overrides,
    builtin_reasoning_aliases,
    list_codex_models,
    DEFAULT_CODEX_MODEL,
)
from .config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = DEFAULT_CODEX_MODEL
_AVAILABLE_MODELS: List[str] = [DEFAULT_MODEL]
_OPENROUTER_MODELS: List[str] = []
_LAST_ERROR: Optional[str] = None
_REASONING_ALIAS_MAP: Dict[str, Tuple[str, ...]] = {}
_WARNED_LEGACY_ENV = False

REASONING_EFFORT_SUFFIXES = ("low", "medium", "high", "xhigh")
OPENROUTER_FALLBACK_MODEL = "gpt-5.1"
OPENROUTER_FALLBACK_EFFORT = "high"
OPENROUTER_DISCOVERY_USER_AGENT = "curl/8.7.1"


def _augment_models(models: List[str]) -> List[str]:
    """Add known aliases (e.g., strip -codex) and remove duplicates."""

    augmented: list[str] = []
    seen = set()
    for model in models:
        if model and model not in seen:
            augmented.append(model)
            seen.add(model)
        if model.endswith('-codex'):
            base = model[:-6]
            if base and base not in seen:
                augmented.append(base)
                seen.add(base)
    return augmented


def _default_reasoning_aliases_for_model(model: str) -> Optional[Tuple[str, ...]]:
    """Return default reasoning effort aliases for well-known model families."""

    normalized = model.rsplit("/", 1)[-1]
    if normalized.startswith("gpt-5"):
        return tuple(REASONING_EFFORT_SUFFIXES)
    return None


def _merge_default_reasoning_aliases(
    models: List[str], alias_map: Dict[str, Tuple[str, ...]]
) -> Dict[str, Tuple[str, ...]]:
    """Ensure models that support reasoning expose aliases even when presets omit them."""

    merged: Dict[str, Tuple[str, ...]] = {k: tuple(v) for k, v in alias_map.items() if v}
    for model in models:
        if model in merged:
            continue
        defaults = _default_reasoning_aliases_for_model(model)
        if defaults:
            merged[model] = defaults
    return merged


async def initialize_model_registry() -> List[str]:
    """Populate the available model list based on Codex CLI presets."""

    global _AVAILABLE_MODELS, _OPENROUTER_MODELS, _LAST_ERROR, _REASONING_ALIAS_MAP

    _warn_if_legacy_env_present()
    apply_codex_profile_overrides()

    try:
        models = await list_codex_models()
        if not models:
            raise CodexError("Codex CLI returned an empty model list")
        _AVAILABLE_MODELS = _augment_models(models)
        _OPENROUTER_MODELS = _load_openrouter_models()
        combined_models = _combined_available_models()
        alias_map = _merge_default_reasoning_aliases(combined_models, builtin_reasoning_aliases())
        _REASONING_ALIAS_MAP = {
            model: tuple(efforts)
            for model, efforts in alias_map.items()
            if efforts and model in combined_models
        }
        if not _REASONING_ALIAS_MAP and "gpt-5" in combined_models:
            _REASONING_ALIAS_MAP = {"gpt-5": tuple(REASONING_EFFORT_SUFFIXES)}
        _LAST_ERROR = None
        logger.info("Loaded %d Codex model(s): %s", len(models), ", ".join(models))
    except Exception as exc:  # pragma: no cover - startup failure path
        _LAST_ERROR = str(exc)
        logger.warning(
            "Falling back to default model list because Codex model discovery failed: %s",
            exc,
        )
        fallback_models = [DEFAULT_MODEL, "gpt-5.1", "gpt-5"]
        _AVAILABLE_MODELS = _augment_models(fallback_models)
        _OPENROUTER_MODELS = _load_openrouter_models()
        fallback_aliases = {
            "gpt-5": tuple(REASONING_EFFORT_SUFFIXES),
            DEFAULT_MODEL: tuple(REASONING_EFFORT_SUFFIXES),
        }
        _REASONING_ALIAS_MAP = _merge_default_reasoning_aliases(
            _combined_available_models(), fallback_aliases
        )
    return _combined_available_models()


def get_available_models(include_reasoning_aliases: bool = False) -> List[str]:
    """Return a copy of the currently cached model list."""

    models = _combined_available_models()
    if include_reasoning_aliases and models:
        for base, suffixes in _REASONING_ALIAS_MAP.items():
            if base not in models:
                continue
            models.extend(f"{base} {suffix}" for suffix in suffixes)
    # Preserve ordering while removing duplicates
    return list(dict.fromkeys(models))


def get_default_model() -> str:
    """Return the default model name used when clients omit `model`."""

    model, _effort, _env, _provider_cfg, _display = resolve_model_request(None)
    return model or (_combined_available_models()[0] if _combined_available_models() else DEFAULT_MODEL)


def choose_model(requested: Optional[str]) -> Tuple[str, Optional[str]]:
    """Validate the requested model name and return the model plus optional reasoning effort."""

    if requested:
        base_model, effort = _split_model_and_effort(requested)
        if base_model in _combined_available_models():
            return base_model, effort
        available = ", ".join(get_available_models(include_reasoning_aliases=True))
        raise ValueError(
            f"Model '{requested}' is not available. Choose one of: {available or 'none'}"
        )
    return get_default_model(), None


def resolve_model_request(
    requested: Optional[str],
) -> Tuple[str, Optional[str], Optional[Dict[str, str]], Optional[Dict[str, str]], str]:
    """Resolve the effective model, reasoning effort, provider env/config, and display label."""

    if requested:
        model, effort = choose_model(requested)
        if model in _OPENROUTER_MODELS:
            if openrouter_enabled():
                return model, effort, _openrouter_env(), _openrouter_codex_overrides(), requested
            return OPENROUTER_FALLBACK_MODEL, OPENROUTER_FALLBACK_EFFORT, None, None, "gpt-5.1 high"
        return model, effort, None, None, requested

    if openrouter_enabled():
        preferred_model = settings.openrouter_model.strip() or (
            _OPENROUTER_MODELS[0] if _OPENROUTER_MODELS else OPENROUTER_FALLBACK_MODEL
        )
        effort = _normalize_reasoning_effort(settings.openrouter_reasoning_effort)
        display = preferred_model if not effort else f"{preferred_model} {effort}"
        return preferred_model, effort, _openrouter_env(), _openrouter_codex_overrides(), display

    return OPENROUTER_FALLBACK_MODEL, OPENROUTER_FALLBACK_EFFORT, None, None, "gpt-5.1 high"


def get_preferred_model_label() -> str:
    """Return the preferred model label for UI defaults."""

    _, _, _, _, display = resolve_model_request(None)
    return display


def get_last_error() -> Optional[str]:
    """Return the most recent discovery error message (if any)."""

    return _LAST_ERROR


def _split_model_and_effort(raw: str) -> Tuple[str, Optional[str]]:
    normalized = " ".join(raw.split()) if raw else ""
    if not normalized:
        return normalized, None
    if " " in normalized:
        base, suffix = normalized.rsplit(" ", 1)
        suffix_lower = suffix.lower()
        supported_suffixes = _REASONING_ALIAS_MAP.get(base)
        if base and suffix_lower in REASONING_EFFORT_SUFFIXES:
            if supported_suffixes and suffix_lower in supported_suffixes:
                return base, suffix_lower
            defaults = _default_reasoning_aliases_for_model(base)
            if defaults and suffix_lower in defaults:
                return base, suffix_lower
    return normalized, None


def _warn_if_legacy_env_present() -> None:
    global _WARNED_LEGACY_ENV
    if _WARNED_LEGACY_ENV:
        return

    legacy_value = os.getenv("CODEX_MODEL")
    if legacy_value:
        logger.warning(
            "Environment variable CODEX_MODEL is deprecated and ignored. Detected value: %s",
            legacy_value,
        )
    _WARNED_LEGACY_ENV = True


def openrouter_enabled() -> bool:
    api_key = settings.openrouter_api_key
    return isinstance(api_key, str) and bool(api_key.strip())


def _combined_available_models() -> List[str]:
    return list(dict.fromkeys([*_OPENROUTER_MODELS, *_AVAILABLE_MODELS]))


def _normalize_reasoning_effort(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in REASONING_EFFORT_SUFFIXES:
        return normalized
    return None


def _openrouter_env() -> Optional[Dict[str, str]]:
    if not openrouter_enabled():
        return None
    return {
        "OPENROUTER_API_KEY": settings.openrouter_api_key.strip(),
    }


def _openrouter_codex_overrides() -> Optional[Dict[str, str]]:
    if not openrouter_enabled():
        return None
    return {
        "model_provider": "openrouter",
        "model_providers.openrouter": (
            '{ name = "OpenRouter", base_url = "'
            + settings.openrouter_base_url.strip().replace('"', '\\"')
            + '", env_key = "OPENROUTER_API_KEY", wire_api = "responses" }'
        ),
    }


def _load_openrouter_models() -> List[str]:
    if not openrouter_enabled():
        return []

    models: List[str] = []
    api_key = settings.openrouter_api_key.strip()
    endpoint = settings.openrouter_base_url.rstrip("/") + "/models"
    req = request.Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": OPENROUTER_DISCOVERY_USER_AGENT,
        },
    )

    try:
        with request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                model_id = entry.get("id")
                if isinstance(model_id, str) and model_id.strip():
                    models.append(model_id.strip())
    except error.URLError as exc:
        logger.warning("Failed to load OpenRouter models from %s: %s", endpoint, exc)
    except Exception as exc:  # pragma: no cover - defensive parsing path
        logger.warning("Failed to parse OpenRouter models from %s: %s", endpoint, exc)

    configured = settings.openrouter_model.strip() if settings.openrouter_model else ""
    if configured and configured not in models:
        models.insert(0, configured)
    return list(dict.fromkeys(models))
