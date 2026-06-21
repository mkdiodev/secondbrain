"""Configuration for the SecondBrain web UI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class LLMEndpoint:
    provider: str
    base_url: str
    model: str


LLMDetector = Callable[[list[LLMEndpoint]], LLMEndpoint | None]


@dataclass(frozen=True)
class UIConfig:
    workspace: str
    ollama_base_url: str
    ollama_model: str
    llm_provider: str = "ollama"
    host: str = "127.0.0.1"
    port: int = 3000

    @classmethod
    def from_env(cls, *, detector: LLMDetector | None = None) -> "UIConfig":
        endpoint = resolve_llm_endpoint(detector=detector)
        return cls(
            workspace=os.environ.get("SECONDBRAIN_WORKSPACE", ".").strip() or ".",
            ollama_base_url=endpoint.base_url,
            ollama_model=endpoint.model,
            llm_provider=endpoint.provider,
            host=os.environ.get("SECONDBRAIN_UI_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=int(os.environ.get("SECONDBRAIN_UI_PORT", "3000")),
        )


def resolve_llm_endpoint(*, detector: LLMDetector | None = None) -> LLMEndpoint:
    provider = os.environ.get("SECONDBRAIN_LLM_PROVIDER", "auto").strip().lower() or "auto"
    if provider in {"lm-studio", "lm_studio"}:
        provider = "lmstudio"
    if provider not in {"auto", "ollama", "lmstudio"}:
        raise ValueError("SECONDBRAIN_LLM_PROVIDER must be auto, ollama, or lmstudio.")

    ollama = LLMEndpoint(
        provider="ollama",
        base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/"),
        model=os.environ.get("OLLAMA_MODEL", "").strip(),
    )
    lmstudio = LLMEndpoint(
        provider="lmstudio",
        base_url=os.environ.get("LM_STUDIO_BASE_URL", "http://localhost:1234/v1").strip().rstrip("/"),
        model=os.environ.get("LM_STUDIO_MODEL", "").strip(),
    )

    if provider == "ollama":
        return _with_default_model(ollama, "gemma4:e2b")
    if provider == "lmstudio":
        return _with_default_model(lmstudio, "local-model")

    candidates = [ollama, lmstudio]
    detected = (detector or detect_running_llm)(candidates)
    if detected is not None:
        return detected
    return _with_default_model(ollama, "gemma4:e2b")


def detect_running_llm(candidates: list[LLMEndpoint]) -> LLMEndpoint | None:
    for candidate in candidates:
        try:
            if candidate.provider == "ollama":
                models = _fetch_ollama_models(candidate.base_url)
            elif candidate.provider == "lmstudio":
                models = _fetch_openai_compatible_models(candidate.base_url)
            else:
                models = []
        except (OSError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
            continue
        model = candidate.model or (models[0] if models else "")
        if model:
            return LLMEndpoint(
                provider=candidate.provider,
                base_url=candidate.base_url,
                model=model,
            )
    return None


def _fetch_ollama_models(base_url: str) -> list[str]:
    payload = _get_json(f"{base_url.rstrip('/')}/api/tags")
    models = payload.get("models", [])
    return [str(item.get("name") or "").strip() for item in models if item.get("name")]


def _fetch_openai_compatible_models(base_url: str) -> list[str]:
    payload = _get_json(f"{base_url.rstrip('/')}/models")
    models = payload.get("data", [])
    return [str(item.get("id") or "").strip() for item in models if item.get("id")]


def _get_json(url: str) -> dict:
    with urlopen(url, timeout=0.35) as response:
        return json.loads(response.read().decode("utf-8"))


def _with_default_model(endpoint: LLMEndpoint, fallback_model: str) -> LLMEndpoint:
    return LLMEndpoint(
        provider=endpoint.provider,
        base_url=endpoint.base_url,
        model=endpoint.model or fallback_model,
    )
