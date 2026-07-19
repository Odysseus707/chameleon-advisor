"""LLM client abstraction.

Default: the Tejas AI OpenAI-compatible endpoint serving
Meta-Llama-3.3-70B-Instruct (matches RAG-docs-chameleon's deployment target).
Fallbacks (opt-in via LLM_PROVIDER):
  - "ollama"    : a local Ollama server (no key, no network, no cost).
  - "anthropic" : the hosted Anthropic API (dev-time, paid).

All clients expose the same `.complete(system, user) -> str` method. Only the
selected one is imported, so the OpenAI/Anthropic SDKs stay optional; the Ollama
client uses the stdlib only, so it needs nothing installed at all.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional, Protocol

from ..config import settings


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class TejasClient:
    """OpenAI-compatible client pointed at the Tejas AI endpoint."""

    name = "tejas"

    def __init__(self):
        from openai import OpenAI  # lazy import

        self.model = settings.tejas_model
        self._client = OpenAI(
            base_url=settings.tejas_base_url,
            api_key=settings.tejas_api_key or "not-needed",
        )

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""


class AnthropicClient:
    """Anthropic dev-time fallback client."""

    name = "anthropic"

    def __init__(self):
        import anthropic  # lazy import

        self.model = settings.anthropic_model
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def complete(self, system: str, user: str) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )


class OllamaClient:
    """Local Ollama client (stdlib only; no key, no cost, fully offline).

    Talks to Ollama's native chat API (POST /api/chat). Requires a running
    `ollama serve` and a pulled model (e.g. `ollama pull llama3`).
    """

    name = "ollama"

    def __init__(self):
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model

    def complete(self, system: str, user: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=settings.http_timeout * 6) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama request to {self.base_url} failed ({exc.reason}). "
                "Is `ollama serve` running and the model pulled?"
            ) from exc
        return (data.get("message") or {}).get("content", "") or ""


def get_llm_client(provider: Optional[str] = None) -> LLMClient:
    """Build the configured client. Raises if its SDK/creds are missing."""
    chosen = (provider or settings.llm_provider or "tejas").lower()
    if chosen in {"tejas", "llama", "openai"}:
        return TejasClient()
    if chosen == "ollama":
        return OllamaClient()
    if chosen == "anthropic":
        return AnthropicClient()
    raise ValueError(
        f"Unknown LLM provider {chosen!r}; expected 'tejas', 'ollama', or 'anthropic'."
    )
