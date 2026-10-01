"""Guards the defect that let the parity gate rot for a month unnoticed.

parity_baseline.py is the only check that catches SILENT RESCORING: a checker
changing behaviour so that already-collected answers score differently. The
golds still pass, the tests still pass, the prompts are unchanged - and every
published number quietly means something else.

It hardcoded `benchmark/items/*.yaml`. The packaging refactor moved the data to
`benchmark/chi_edge_bench/data/items/`, so every invocation exited with "glob
matched no files". It failed closed, which is the right failure - but nothing
ran it in CI, so nobody noticed, and the surface went unprotected.

These tests are cheap and run with the normal suite. They assert the gate can
still LOCATE what it protects. They deliberately do not assert file counts:
that is test_paths.py's job, and duplicating it here would make adding one item
fail two tests for one reason.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent
TOOL = BENCH / "corpus_v2" / "tools" / "parity_baseline.py"


def _load():
    """Import the tool by path. It is a standalone script, not a package
    module, so there is no import route to it other than this."""
    spec = importlib.util.spec_from_file_location("parity_baseline", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def parity():
    if not TOOL.is_file():
        pytest.skip(f"{TOOL} not present")
    return _load()


def test_at_least_one_wing_is_discovered(parity):
    """Zero wings means the discovery rule no longer matches the repo layout."""
    wings = parity.discover_wings()
    assert wings, "no benchmark wing discovered"
    names = [n for n, _d in wings]
    assert "chi_edge_bench" in names, f"edge wing missing from {names}"


def test_every_discovered_wing_contributes_files(parity):
    """A wing matching zero patterns is Level 1 going blind to that wing.

    This is the assertion that would have caught the original bug on the day
    the packaging refactor landed.
    """
    counts = parity.manifest_wing_counts()
    empty = [n for n, c in counts.items() if c == 0]
    assert not empty, f"wings watched but contributing no files: {empty}"


def test_content_manifest_is_non_empty_and_resolves(parity):
    rows = parity.content_manifest()
    assert rows, "content manifest is empty"
    workspace = parity.WORKSPACE
    missing = [k for k, _d in rows if not (workspace / k).is_file()]
    assert not missing, f"manifest names files that do not exist: {missing[:5]}"


def test_capability_table_is_watched(parity):
    """It is hand-authored ground truth behind every reservation verdict, and
    the original four globs did not cover it at all."""
    keys = [k for k, _d in parity.content_manifest()]
    assert any(k.endswith("capability_table.yaml") for k in keys), \
        "capability_table.yaml is not in the watched surface"


def test_items_grounding_and_snapshots_are_watched(parity):
    """The original surfaces must still resolve under the new patterns."""
    keys = [k for k, _d in parity.content_manifest()]
    for marker in ("/items/", "/grounding/", "/snapshots/", "/extractions/"):
        assert any(marker in k for k in keys), f"nothing watched under {marker}"


def _subprocess_module_targets() -> list[str]:
    """The `-m` targets the tool actually invokes, read out of its source.

    Deliberately NOT a hardcoded list. A second list of module names is the
    same failure mode as the hardcoded path that caused all this: it drifts
    from the thing it describes and nothing notices. Parsing the source means
    the test tracks the tool instead of shadowing it.
    """
    src = TOOL.read_text(encoding="utf-8")
    return re.findall(r'"-m",\s*"([A-Za-z_][\w.]*)"', src)


def test_subprocess_targets_are_discoverable():
    """If this finds nothing, the parser broke and the next test is vacuous."""
    targets = _subprocess_module_targets()
    assert targets, "no '-m <module>' subprocess targets found in the gate"


def test_subprocess_targets_are_importable():
    """Level 2 and Level 3 shell out to these by module path.

    The same refactor left this file calling `-m harness.validate_golds`, which
    had also moved. A stale subprocess target fails at run time, not import
    time, so only actually resolving it proves the gate can run.
    """
    for module in _subprocess_module_targets():
        proc = subprocess.run([sys.executable, "-c", f"import {module}"],
                              capture_output=True, text=True, cwd=BENCH)
        assert proc.returncode == 0, \
            f"gate calls `-m {module}` but it is not importable: " \
            f"{proc.stderr.strip()[:300]}"


def test_tool_has_no_hardcoded_pre_package_paths():
    """The literal shape of the original bug, kept out by assertion.

    `BENCH / "items"` and friends are the pre-package layout. If they reappear,
    the gate is pointing at directories that have not existed since the wheel
    was created.
    """
    src = TOOL.read_text(encoding="utf-8")
    for bad in ('BENCH / "items"', 'BENCH / "grounding"', 'BENCH / "snapshots"',
                'BENCH / "extractions"', 'BENCH / "tools"',
                '"-m", "harness.'):
        assert bad not in src, f"pre-package path resurfaced in the gate: {bad}"
