"""Central settings module.

Everything configurable lives here and is sourced from environment variables
(optionally loaded from a .env file). Nothing about the availability backend or
API keys is hardcoded elsewhere in the package -- callers read `settings`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no external dependency).

    Only sets variables that are not already present in the environment, so
    real environment variables always win over the .env file.
    """
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


# Load .env from the package root / cwd once at import time.
_PKG_ROOT = Path(__file__).resolve().parent.parent
for _candidate in (_PKG_ROOT / ".env", Path.cwd() / ".env"):
    _load_dotenv(_candidate)


def _get_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of runtime configuration."""

    # --- Availability backend selection (never hardcoded at call sites) ---
    # One of: "reference_api", "blazar".
    availability_backend: str = field(
        default_factory=lambda: os.environ.get("AVAILABILITY_BACKEND", "reference_api")
    )

    # --- Reference / discovery API ---
    reference_api_base: str = field(
        default_factory=lambda: os.environ.get(
            "REFERENCE_API_BASE", "https://api.chameleoncloud.org"
        )
    )
    edge_site_uid: str = field(
        default_factory=lambda: os.environ.get("EDGE_SITE_UID", "edge")
    )

    # --- Chameleon / Blazar (python-chi) ---
    chi_site_name: str = field(
        default_factory=lambda: os.environ.get("CHI_SITE_NAME", "CHI@Edge")
    )
    chi_project_name: Optional[str] = field(
        default_factory=lambda: os.environ.get("CHI_PROJECT_NAME") or None
    )

    # Glob of Chameleon application-credential openrc files, one per site
    # (a credential is scoped to a single site). Consumed by BlazarBackend.
    chameleon_rc_glob: Optional[str] = field(
        default_factory=lambda: os.environ.get("CHAMELEON_RC_GLOB") or None
    )

    # --- LLM reasoner (OpenAI-compatible client) ---
    # Default: Tejas AI endpoint serving Meta-Llama-3.3-70B-Instruct.
    llm_provider: str = field(
        default_factory=lambda: os.environ.get("LLM_PROVIDER", "tejas")
    )
    tejas_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "TEJAS_BASE_URL", "https://ai.tejas.tacc.utexas.edu/v1"
        )
    )
    tejas_model: str = field(
        default_factory=lambda: os.environ.get(
            "TEJAS_MODEL", "Meta-Llama-3.3-70B-Instruct"
        )
    )
    tejas_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("TEJAS_API_KEY") or None
    )
    # Anthropic dev-time fallback (opt-in via LLM_PROVIDER=anthropic).
    anthropic_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY") or None
    )
    anthropic_model: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
    )
    # Local Ollama (opt-in via LLM_PROVIDER=ollama). Runs fully offline, no key,
    # no cost. Talks to Ollama's native chat API over stdlib HTTP.
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
    )
    ollama_model: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_MODEL", "llama3")
    )

    # --- Embeddings / vector store (mirror RAG-docs-chameleon) ---
    embedding_model: str = field(
        default_factory=lambda: os.environ.get(
            "EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5"
        )
    )

    # --- Paths ---
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("DATA_DIR", str(_PKG_ROOT / "data"))
        )
    )
    # Flattened Trovi artifacts (README + main.md per artifact). Defaults to the
    # sibling `grounding/` directory produced alongside this package.
    grounding_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("GROUNDING_DIR", str(_PKG_ROOT.parent / "grounding"))
        )
    )
    # Force the pure-Python offline path even if faiss/bge/openai are installed
    # (used by tests and for credential-free demos).
    offline: bool = field(
        default_factory=lambda: _get_bool("ADVISOR_OFFLINE", False)
    )

    # --- Logging ---
    log_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get("ADVISOR_LOG_PATH", str(_PKG_ROOT / "data" / "runs.jsonl"))
        )
    )

    http_timeout: float = field(
        default_factory=lambda: float(os.environ.get("HTTP_TIMEOUT", "20"))
    )

    @property
    def inventory_cache_path(self) -> Path:
        return self.data_dir / "chi_edge_inventory.json"


settings = Settings()
