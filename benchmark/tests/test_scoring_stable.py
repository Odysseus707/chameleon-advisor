"""Scoring must not drift.

The shipped baselines are the exact CSVs the project's published results were
computed from. Re-scoring the same answers must reproduce them byte for byte:
if it does not, a refactor has silently changed a measurement and every
published number is suspect.

Skipped when the answer record is absent, which is the normal case for an
installed copy - the runs are not shipped, only the scores they produced.
"""
import csv

import pytest

from chi_edge_bench.paths import baselines_dir, runs_dir
from chi_edge_bench.tools.score_runs import score_all

BASELINES = {
    "tejas_scores.csv": ["s10-llama70b-tejas-noadv", "s10-llama70b-tejas-adv"],
    "isolation_scores.csv": ["s10-llama70b-tejas-noadv", "s10-llama70b-tejas-adv",
                             "s11-llama70b-heuristic-adv"],
}


def _rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("name,systems", BASELINES.items())
def test_rescoring_reproduces_the_shipped_baseline(name, systems):
    ref_path = baselines_dir() / name
    ref = _rows(ref_path)
    have = {d.name for d in runs_dir().glob("*/*")}
    if not set(systems) <= have:
        pytest.skip(f"answer record for {systems} not present in {runs_dir()}")

    conditions = {r["condition"] for r in ref}
    got = score_all(conditions, set(systems), wrap_code=False, suite="")
    assert len(got) == len(ref), "row count changed"

    key = lambda r: (r["condition"], r["system"], r["item"])  # noqa: E731
    for a, b in zip(sorted(got, key=key), sorted(ref, key=key)):
        for field in ref[0]:
            assert str(a[field]) == b[field], (
                f"{a['condition']}/{a['system']}/{a['item']}.{field}: "
                f"{a[field]!r} != {b[field]!r}")
