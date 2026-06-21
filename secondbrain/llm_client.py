"""Async HTTP client for a local LLM (Ollama-compatible API)."""

from __future__ import annotations

from typing import Any, Dict, List


class LocalLLMClient:
    """Talks to a local Ollama or OpenAI-compatible local LLM server."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "gemma4:e2b",
        provider: str = "ollama",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """Send a chat completion request and return the assistant's text."""
        try:
            import aiohttp
        except ImportError as exc:
            raise ImportError(
                "aiohttp is required for the LLM client. "
                "Install it with: pip install aiohttp"
            ) from exc

        if self.provider in {"lmstudio", "openai-compatible"}:
            url = f"{self.base_url}/chat/completions"
            payload: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "temperature": temperature,
            }
        else:
            url = f"{self.base_url}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"LLM returned HTTP {resp.status}: {text}")
                data = await resp.json()
                if self.provider in {"lmstudio", "openai-compatible"}:
                    return data["choices"][0]["message"]["content"]
                return data["message"]["content"]
