"""The wing seam: two benchmarks in one tree, and the edge one must not move.

Everything here exists to defend one property. The edge wing's 134 items and
3231 collected answer cells are frozen and already published, so a caller that
does not ask for a wing must behave byte-identically to how it behaved before
wings existed. These are the tests that make "must" mean something.
"""
import pytest

from chi_edge_bench import paths
from chi_edge_bench.harness import checks

CHAMELEON = "chameleon_bench"


@pytest.fixture(autouse=True)
def _restore_wing():
    """No test may leak wing state into the next one.

    Without this the suite itself becomes the hazard it is testing for: a test
    that pins the chameleon wing and dies would leave every later test grading
    against the wrong data, and they would mostly still pass.
    """
    yield
    paths.set_wing(None)


# -- the default is the edge wing, exactly as before -----------------------

def test_default_wing_is_edge():
    assert paths.wing() == paths.DEFAULT_WING == "chi_edge_bench"


def test_default_wing_data_is_DATA_itself():
    """Identity, not equality. Two spellings of the same directory can differ
    by a resolve() or a symlink; `is` cannot."""
    assert paths.wing_data() is paths.DATA


@pytest.mark.parametrize("accessor", [
    "items_dir", "snapshots_dir", "grounding_dir", "extractions_dir",
    "baselines_dir", "capability_table", "artifacts_dir", "default_snapshot",
])
def test_every_accessor_defaults_under_edge_data(accessor):
    assert str(getattr(paths, accessor)()).startswith(str(paths.DATA))


def test_edge_data_still_ships_its_items():
    assert len(list(paths.items_dir().glob("*.yaml"))) == 134


# -- switching wings actually switches -------------------------------------

def test_known_wings_lists_both_with_edge_first():
    known = paths.known_wings()
    assert known[0] == paths.DEFAULT_WING
    assert CHAMELEON in known


def test_set_wing_moves_the_accessors():
    paths.set_wing(CHAMELEON)
    assert paths.wing() == CHAMELEON
    assert len(list(paths.grounding_dir().glob("A*.md"))) == 90
    assert len(list(paths.artifacts_dir().glob("A*.yaml"))) == 90


def test_set_wing_none_restores_the_edge_default():
    paths.set_wing(CHAMELEON)
    paths.set_wing(None)
    assert paths.wing() == paths.DEFAULT_WING
    assert paths.wing_data() is paths.DATA


def test_unknown_wing_fails_loudly_rather_than_globbing_nothing():
    """A typo must not resolve to a missing directory and surface later as an
    empty item set - "this wing has no items" is what a real failure looks like."""
    with pytest.raises(SystemExit) as e:
        paths.set_wing("no_such_bench")
    assert "no_such_bench" in str(e.value)


def test_a_rejected_wing_does_not_change_the_current_one():
    with pytest.raises(SystemExit):
        paths.set_wing("no_such_bench")
    assert paths.wing() == paths.DEFAULT_WING


# -- the capability-table cache hazard -------------------------------------

def test_captable_cache_is_keyed_by_path(tmp_path):
    """The Level 2 hazard, as a test.

    _captable was lru_cache(maxsize=1) over a no-argument function. With two
    wings that means the first table parsed wins for the rest of the process:
    score a chameleon item, then rescore an edge answer, and CHI@Edge gets
    graded against bare-metal hardware. Golds pass, tests pass, and every
    published edge number quietly means something else.
    """
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("device_types:\n  alpha:\n    ram_gb: 1\n")
    b.write_text("node_types:\n  beta:\n    ram_gb: 2\n")
    assert set(checks._captable_at(str(a))) == {"alpha"}
    assert set(checks._captable_at(str(b))) == {"beta"}
    # and back again - a second read of `a` must not return b's contents
    assert set(checks._captable_at(str(a))) == {"alpha"}


def test_captable_accepts_either_top_level_key(tmp_path):
    """Edge reserves devices, chameleon reserves hosts. Forcing bare-metal
    nodes to be called "devices" would put a wrong word in hand-authored
    ground truth to save a line of parsing."""
    f = tmp_path / "t.yaml"
    f.write_text("node_types:\n  compute_skylake:\n    ram_gb: 192\n")
    assert checks._captable_at(str(f))["compute_skylake"]["ram_gb"] == 192


def test_captable_with_no_recognised_block_fails_loudly(tmp_path):
    f = tmp_path / "t.yaml"
    f.write_text("version: '1.0'\n")
    with pytest.raises(SystemExit):
        checks._captable_at(str(f))


def test_edge_capability_table_still_parses_through_the_new_path():
    tbl = checks._captable()
    assert "raspberrypi4-64" in tbl


# -- snapshot typing --------------------------------------------------------

def test_snapshot_counts_reads_node_type_as_well_as_device_type(tmp_path):
    """A bare-metal capture types a host with Blazar's own `node_type`. The
    fallback must never fire on an edge snapshot - they all carry device_type -
    so it cannot move an edge verdict."""
    import json
    f = tmp_path / "s.json"
    f.write_text(json.dumps({"devices": [
        {"node_type": "compute_skylake", "status": "free"},
        {"node_type": "compute_skylake", "status": "down"},
    ]}))
    counts = checks._snapshot_counts(str(f))
    assert counts["compute_skylake"] == {"free": 1, "total": 2}


def test_every_edge_snapshot_still_types_by_device_type():
    """The guard on the guard: if an edge snapshot ever lacked device_type, the
    fallback above would start firing on frozen data."""
    import json
    for snap in paths.snapshots_dir().glob("*.json"):
        devices = json.loads(snap.read_text())["devices"]
        assert all("device_type" in d for d in devices), snap.name


# -- a gate that matched nothing must not exit green ------------------------
# P10's shape: a check that did not run reads exactly like a check that passed.
# --suite lost its argparse `choices` when wings gained their own suite names,
# so a typo is now reachable and has to fail loudly instead of reporting 0/0.

import subprocess
import sys


def _run(module, *args):
    return subprocess.run([sys.executable, "-m", module, *args],
                          capture_output=True, text=True)


@pytest.mark.parametrize("module", [
    "chi_edge_bench.harness.validate_golds",
    "chi_edge_bench.harness.tier_assign",
])
@pytest.mark.parametrize("args", [
    # A wing/suite pair that matches nothing. Not "--wing chameleon_bench"
    # alone: that wing has items now, and a test whose premise expires silently
    # starts asserting something it no longer means.
    ("--wing", CHAMELEON, "--suite", "core"),
    ("--suite", "cor"),         # a typo'd suite name
])
def test_matching_no_items_exits_nonzero(module, args):
    r = _run(module, *args)
    assert r.returncode != 0, (
        f"{module} {' '.join(args)} matched nothing and still exited 0 - "
        f"that is a gate reporting success for a run that never happened.\n"
        f"{r.stdout}{r.stderr}")
    assert "Refusing" in (r.stdout + r.stderr)


def test_the_edge_core_gate_still_exits_zero():
    """The other half: the refusal must not have become a blanket failure."""
    r = _run("chi_edge_bench.harness.validate_golds", "--suite", "core")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "50/50" in r.stdout
