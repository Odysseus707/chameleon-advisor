"""Computed tiers must match what each item claims (decisions D04/D14).

Tiers are measured from key-token coverage of the fed grounding, never asserted
by the author, so a mismatch means the item's stated intent and its actual
grounding coverage disagree.
"""
from chi_edge_bench.harness.tier_assign import _load_grounding, assign
from chi_edge_bench.paths import items_dir

import pytest
import yaml


def _pairs():
    for p in sorted(items_dir().glob("*.yaml")):
        item = yaml.safe_load(p.read_text())
        for cond, fed in item.get("fed_sets", {}).items():
            yield item, cond, fed


def test_no_tier_intent_mismatches():
    grounding = _load_grounding()
    mismatches = []
    for item, cond, fed in _pairs():
        intent = item.get("tier_intent_by_condition", {}).get(cond)
        if not intent:
            continue
        got = assign(item, fed, grounding)["tier"]
        if got != intent:
            mismatches.append(f"{item['id']}/{cond}: got {got}, intended {intent}")
    assert not mismatches, "\n".join(mismatches)


def test_every_item_declares_blind():
    """blind is the uncontaminated arm every comparison is anchored on."""
    undeclared = sorted({item["id"] for item, _, _ in _pairs()
                         if "blind" not in item.get("fed_sets", {})})
    assert not undeclared, f"items with no blind condition: {undeclared}"


def test_main_runs_to_completion(capsys, tmp_path, monkeypatch):
    """Exercises main(), not just assign().

    A test that only called assign() missed a NameError on main()'s very last
    line: the rows all printed, so the failure looked like truncated output.
    """
    import sys

    from chi_edge_bench import paths
    from chi_edge_bench.harness import tier_assign

    paths.set_workspace(tmp_path)
    monkeypatch.setattr(sys, "argv", ["tier_assign", "--suite", "core"])
    try:
        with pytest.raises(SystemExit) as e:
            tier_assign.main()
    finally:
        paths.set_workspace(None)
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "mismatches" in out
    assert (tmp_path / "exports" / "tier_report.json").is_file()
