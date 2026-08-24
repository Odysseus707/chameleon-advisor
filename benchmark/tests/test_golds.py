"""The install gate.

Decision D06: an item is only part of the benchmark if its own gold passes 100%
of its own checkers. A failing gold is a defective item, never a defective gold.

Promoted from a script to a test because it is the strongest single proof that
an install is sound: it exercises the items, the checkers, the capability table
and the snapshots together, and needs no network, no key and no model.
"""
import yaml

import pytest

from chi_edge_bench.harness.runner import evaluate
from chi_edge_bench.harness.validate_golds import as_answer
from chi_edge_bench.paths import default_snapshot, items_dir

ITEMS = sorted(items_dir().glob("*.yaml"))


def _load(path):
    return yaml.safe_load(path.read_text())


def test_the_item_bank_is_the_expected_size():
    """134 items in two suites. A wrong count means data did not ship."""
    suites = {}
    for p in ITEMS:
        suites.setdefault(_load(p).get("suite", "core"), []).append(p.stem)
    assert len(ITEMS) == 134
    assert len(suites["core"]) == 50
    assert len(suites["reservation"]) == 84


@pytest.mark.parametrize("path", ITEMS, ids=lambda p: p.stem)
def test_gold_passes_its_own_checkers(path):
    item = _load(path)
    rep = evaluate(item, as_answer(item), default_snapshot())
    if not rep["all_passed"]:
        failed = [f"{r['check']}[{r['group']}]: {r['detail']}"
                  for r in rep["results"] if not r["passed"]]
        pytest.fail(f"{item['id']} gold fails its own checkers:\n  "
                    + "\n  ".join(failed))
