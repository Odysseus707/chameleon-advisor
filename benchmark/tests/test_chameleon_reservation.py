"""The baremetal_reservation suite and the capability table it rests on.

Feasibility is computed from a recorded snapshot; capability is hand-authored
vendor fact. The two are kept strictly apart, and these tests are what stops
them merging by accident - once they blend, nobody can say which half of a
verdict was measured and which was asserted.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from chi_edge_bench import paths
from chi_edge_bench.harness.runner import evaluate
from chi_edge_bench.harness.validate_golds import as_answer

BENCH = Path(__file__).resolve().parent.parent
WING = BENCH / "chameleon_bench" / "data"
SUITE = "baremetal_reservation"
sys.path.insert(0, str(BENCH / "corpus_v2" / "tools"))
import build_reservation_items as R  # noqa: E402


@pytest.fixture(autouse=True)
def _wing():
    """Pin the wing for every test here.

    Without this, snapshots_dir() and the capability table resolve to the EDGE
    wing, and a reservation gold gets graded against CHI@Edge hardware. It
    fails loudly rather than silently, but only because the data does not
    overlap; pinning removes the coincidence.
    """
    paths.set_wing("chameleon_bench")
    yield
    paths.set_wing(None)


@pytest.fixture(scope="module")
def table():
    return yaml.safe_load((WING / "capability_table.yaml").read_text())


@pytest.fixture(scope="module")
def items():
    out = [yaml.safe_load(p.read_text()) for p in sorted((WING / "items").glob("RB*.yaml"))]
    assert out, "no reservation items on disk"
    return out


# -- the table --------------------------------------------------------------

def test_table_covers_every_node_type_in_both_captures(table):
    listed = set(table["node_types"])
    for snap in (WING / "snapshots").glob("baremetal_*.json"):
        doc = json.loads(snap.read_text())
        if doc["_meta"].get("SYNTHETIC"):
            continue
        live = {d["node_type"] for d in doc["devices"]}
        assert live <= listed, f"{snap.name} has types absent from the table: {live - listed}"


def test_every_type_records_which_sites_it_is_at(table):
    """gpu_rtx_6000 is CHI@UC only and gpu_mi100 is CHI@TACC only. A table that
    lost that would let the solver recommend hardware to the wrong site."""
    for t, v in table["node_types"].items():
        assert v.get("sites"), f"{t} records no site"
        assert all(s in ("CHI@UC", "CHI@TACC") for s in v["sites"]), t
        assert sum(v["sites"].values()) == v["node_count"], t


def test_accelerator_vocabulary_is_closed(table):
    allowed = {"none", "cuda", "rocm", "oneapi", "fpga"}
    for t, v in table["node_types"].items():
        assert v["accelerator"] in allowed, f"{t}: {v['accelerator']}"


def test_only_cuda_parts_carry_cuda_compute(table):
    """The MI100 is AMD and the Ponte Vecchio is Intel. Giving either a CUDA
    compute capability would make the accelerator-confusion trap unfindable -
    a CUDA filter would accept them."""
    for t, v in table["node_types"].items():
        if v["accelerator"] != "cuda":
            assert v["cuda_compute"] is None, f"{t} is {v['accelerator']} but has cuda_compute"
            assert not v["cuda_cores"], f"{t} is {v['accelerator']} but has cuda_cores"


def test_mi100_is_rocm_not_cuda(table):
    mi = table["node_types"]["gpu_mi100"]
    assert mi["accelerator"] == "rocm" and mi["cuda_compute"] is None


def test_measured_fields_are_null_not_guessed(table):
    """Blazar reports nothing for many hosts. A null there is honest; a zero or
    an invented number would be a measurement of absence."""
    for t, v in table["node_types"].items():
        for f in ("ram_gb", "vcpus"):
            assert v[f] is None or isinstance(v[f], int), f"{t}.{f} = {v[f]!r}"


def test_capability_never_comes_from_an_artifact(table):
    """covered_by is corpus provenance and must not imply capability: types with
    no artifact coverage still carry full vendor facts."""
    uncovered = [t for t, v in table["node_types"].items() if not v["covered_by"]]
    assert len(uncovered) >= 10, "expected many uncovered types; the point of the table"
    for t in uncovered:
        assert table["node_types"][t]["accelerator"] is not None


# -- the items --------------------------------------------------------------

def test_suite_and_size(items):
    """Pinned, not `>=`. The bank is 8 stems x 12 bare-metal snapshots, and a
    loose bound would have sat green through a generator that silently emitted
    half of them."""
    assert len(items) == 96, len(items)
    assert {i["suite"] for i in items} == {SUITE}


def test_every_baremetal_snapshot_carries_items(items):
    """Phase M exists because nine of fourteen snapshots graded nothing. The
    perturbed environments are what exercise the ladder's busy, future and
    expansion rungs; an unused one is a rung nobody measured."""
    from chi_edge_bench import paths
    snaps = {p.stem for p in paths.snapshots_dir().glob("baremetal_*.json")}
    used = {i["snapshot"] for i in items}
    assert snaps - used == set(), f"snapshots grading nothing: {sorted(snaps - used)}"
    assert len(used) == 12


def test_ids_are_contiguous_and_positional(items):
    """RB ids are the loop index. A gap means an environment was inserted or
    reordered rather than appended, which re-points collected answers at
    different questions without changing a single filename."""
    ids = sorted(i["id"] for i in items)
    assert ids == [f"RB{n:02d}" for n in range(1, 97)]


def test_every_gold_passes_its_own_checkers(items):
    for i in items:
        rep = evaluate(i, as_answer(i), None)
        bad = [r["check"] for r in rep["results"] if not r["passed"]]
        assert rep["all_passed"], f"{i['id']} gold fails: {bad}"


def test_every_item_names_a_snapshot_that_exists(items):
    for i in items:
        assert (WING / "snapshots" / f"{i['snapshot']}.json").is_file(), i["id"]


def test_infeasible_items_state_the_coverage_limitation(items):
    """A refusal that does not say why reads the same as not knowing."""
    for i in items:
        if not i["feasible"]:
            assert "no artifact" in i["gold_spec"].lower(), i["id"]


def test_recommended_types_exist_at_the_item_site(items, table):
    """The cross-site error, gated. Recommending gpu_rtx_6000 at CHI@TACC is
    wrong in a way no amount of waiting fixes."""
    for i in items:
        for c in i["checkers"]:
            for t in c.get("allowed", []):
                assert i["site"] in table["node_types"][t]["sites"], \
                    f"{i['id']} allows {t}, absent from {i['site']}"


def test_both_feasible_and_infeasible_items_exist(items):
    """A suite that is all-feasible measures nothing about refusal, and one that
    is all-infeasible measures nothing about choosing.

    The invariant is that BOTH classes are populated; the exact split is
    asserted underneath it only as a drift detector. It moved 64/32 -> 68/28
    when the capability table was refilled from the reference API: RB20, RB36,
    RB60 and RB76 are big_memory items that had been declared infeasible
    because every candidate's ram_gb was null, and under R4 a null fails a
    minimum. Those four were wrong about the testbed, not strict about it.
    """
    feasible = sum(i["feasible"] for i in items)
    assert 0 < feasible < len(items), "one class is empty; the suite measures half of what it claims"
    assert feasible == 68
    assert sum(not i["feasible"] for i in items) == 28


def test_prompt_provenance(items):
    import hashlib
    for i in items:
        assert i["prompt_sha256"] == hashlib.sha256(i["prompt"].encode()).hexdigest(), i["id"]


# -- the solver -------------------------------------------------------------

def test_rebuilding_is_a_no_op():
    """R5. A gate that goes red on a no-op is one people learn to ignore."""
    r = subprocess.run([sys.executable, str(BENCH / "corpus_v2" / "tools" /
                        "build_reservation_items.py")],
                       capture_output=True, text=True, cwd=BENCH)
    assert r.returncode == 0, r.stderr
    tail = [l for l in r.stdout.splitlines() if "item(s);" in l]
    assert tail and tail[-1].strip().split(";")[1].strip().startswith("0 written"), tail


def test_solver_excludes_hardware_absent_from_the_site(table):
    ranked, _ = R.solve({"requires": {"accelerator": "rocm"}, "count": 1},
                        "baremetal_uc_2026-09-04", "CHI@UC", table)
    assert ranked == [], "gpu_mi100 is CHI@TACC only; CHI@UC cannot satisfy rocm"


def test_solver_will_not_offer_an_mi100_for_cuda(table):
    ranked, rejected = R.solve({"requires": {"accelerator": "cuda"}, "count": 1},
                               "baremetal_tacc_abundant_2026-09-04", "CHI@TACC", table)
    assert "gpu_mi100" not in [n for n, _, _ in ranked]
    assert any(n == "gpu_mi100" and "accelerator" in w for n, w, _ in rejected)


def test_solver_treats_an_unknown_measurement_as_failing_a_minimum(table):
    """Blazar not reporting a host's RAM is not evidence that it has enough."""
    spec = {"ram_gb": None, "accelerator": "none"}
    assert R.meets(spec, {"min_ram_gb": 180}) is not None
