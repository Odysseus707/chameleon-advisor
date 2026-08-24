"""Adapters must be constructible without credentials.

A stranger's first command is a --dry-run. If that needs a key, the benchmark
looks unusable before they have decided whether to spend anything.
"""
import pytest

from chi_edge_bench.tools import run_bench


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY",
                "OPENAI_BASE_URL", "LLM_API_BASE"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("cls", [run_bench.OpenAIAdapter,
                                 run_bench.AnthropicAdapter])
def test_dry_run_needs_no_key(cls):
    cls().prepare({}, dry_run=True)


def test_openai_defaults_to_the_real_endpoint():
    a = run_bench.OpenAIAdapter()
    a.prepare({}, dry_run=True)
    assert a.base_url == run_bench.OPENAI_DEFAULT_BASE


def test_openai_takes_a_base_url_from_config():
    a = run_bench.OpenAIAdapter()
    a.prepare({"openai": {"base_url": "http://localhost:11434/v1"}}, dry_run=True)
    assert a.base_url == "http://localhost:11434/v1"


def test_openai_takes_a_base_url_from_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://vllm.internal:8000/v1")
    a = run_bench.OpenAIAdapter()
    a.prepare({}, dry_run=True)
    assert a.base_url == "http://vllm.internal:8000/v1"


def test_real_openai_without_a_key_is_refused():
    """Only api.openai.com genuinely requires one, and it must say so."""
    with pytest.raises(SystemExit) as e:
        run_bench.OpenAIAdapter().prepare({}, dry_run=False)
    assert "--base-url" in str(e.value)


def test_self_hosted_without_a_key_is_allowed():
    """Ollama and vLLM ignore the key; demanding one blocks the free path.

    Stops at the SDK import, which is the `openai` extra - not at the key.
    """
    a = run_bench.OpenAIAdapter()
    try:
        a.prepare({"openai": {"base_url": "http://localhost:11434/v1"}},
                  dry_run=False)
    except SystemExit as exc:               # pragma: no cover
        pytest.fail(f"a self-hosted endpoint should not need a key: {exc}")
    except ImportError:
        pass                                # openai SDK not installed here
