"""Guards the defect that proved the benchmark needed packaging.

runner.py used `from checks import run_checks` while score_runs.py used
`from harness.checks import ...`. Both ran in one process, so one file became
two module objects with two copies of the capability-table lru_cache. Nothing
failed loudly; it was only visible by identity-checking the modules.
"""
import importlib
import pkgutil
import sys

import pytest

import chi_edge_bench

TOOL_MODULES = sorted(
    m.name for m in pkgutil.walk_packages(chi_edge_bench.__path__,
                                          "chi_edge_bench.")
)


def test_checks_has_one_identity():
    import chi_edge_bench.harness.checks as direct
    import chi_edge_bench.tools.score_runs  # noqa: F401  the other old route
    assert sys.modules["chi_edge_bench.harness.checks"] is direct


@pytest.mark.parametrize("bare", ["checks", "runner", "harness", "provenance",
                                  "calibrate_v3", "tier_assign"])
def test_no_module_leaks_to_the_top_level(bare):
    """A bare name in sys.modules means someone is still sys.path.insert-ing."""
    importlib.import_module("chi_edge_bench.tools.score_runs")
    assert bare not in sys.modules


@pytest.mark.parametrize("name", TOOL_MODULES)
def test_every_module_imports(name):
    """Optional extras may raise ImportError; nothing else may raise at all.

    In particular nothing may raise SystemExit: score_runs imports calibrate_v3
    behind `except ImportError` to keep fence recovery optional, and a
    SystemExit there takes the scorer down over a missing spreadsheet library.
    """
    try:
        importlib.import_module(name)
    except ImportError as exc:
        assert "pip install" in str(exc), (
            f"{name} raised a bare ImportError; it should name the extra")


def test_scorer_survives_without_optional_extras():
    m = importlib.import_module("chi_edge_bench.tools.score_runs")
    assert hasattr(m, "score_all")
