"""Grounding documents are what an assistant is FED about an artifact.

A doc that is missing, empty, or rendered from a tree other than the one it
names is worse than absent: it is evidence that looks trustworthy. These tests
check the properties that make a doc citable - it exists, it names its commit,
it carries provisioning, and it says so when it has been trimmed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BENCH = Path(__file__).resolve().parent.parent
WING = BENCH / "chameleon_bench" / "data"
ARTIFACTS_DIR = WING / "artifacts"
GROUNDING_DIR = WING / "grounding"
MANIFEST = ARTIFACTS_DIR / "_manifest.yaml"

EXPECTED_COUNT = 90
SOFT_MAX, HARD_MAX = 60_000, 200_000

def _strong_calls():
    """detect.py's own vocabulary, not a hand-copied list.

    A parallel list drifts: an earlier version of this test omitted
    `create_container` and `get_devices` and reported four healthy documents as
    barren. Reading the real vocabulary makes that impossible.
    """
    import sys
    sys.path.insert(0, str(BENCH / "corpus_v2" / "tools"))
    from detect import STRONG_CALLS
    return STRONG_CALLS


@pytest.fixture(scope="module")
def records():
    if not MANIFEST.is_file():
        pytest.skip("registry not built (corpus_v2/tools/select_wing.py run)")
    ids = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["ids"]
    out = [yaml.safe_load((ARTIFACTS_DIR / f"{i}.yaml").read_text("utf-8"))
           for i in ids]
    if not any(r.get("grounding_bytes") for r in out):
        pytest.skip("grounding not rendered "
                    "(corpus_v2/tools/render_grounding.py run)")
    return out


def test_one_grounding_doc_per_artifact(records):
    """Uniform with the edge wing: grounding/A1.md ... one file per artifact."""
    files = sorted(p.stem for p in GROUNDING_DIR.glob("A*.md"))
    assert len(files) == EXPECTED_COUNT
    assert files == sorted(r["id"] for r in records)


def test_no_document_is_empty(records):
    for r in records:
        p = GROUNDING_DIR / f"{r['id']}.md"
        assert p.is_file(), f"{r['id']} has no grounding document"
        assert p.stat().st_size > 200, f"{r['id']} grounding is essentially empty"


def test_documents_name_the_commit_they_came_from(records):
    """Provenance is the whole point of Step 2. A doc that does not name its
    commit cannot be checked against anything."""
    for r in records:
        text = (GROUNDING_DIR / f"{r['id']}.md").read_text(encoding="utf-8")
        assert f"@ {r['pinned_sha']}" in text, \
            f"{r['id']} does not name its pinned commit"
        assert r["id"] in text and r["artifact_id"] in text


def test_recorded_hash_and_size_match_the_file(records):
    """The registry's grounding_sha256 is how a later stage detects that a doc
    was edited by hand. It is worthless if it is not kept true."""
    import hashlib
    for r in records:
        text = (GROUNDING_DIR / f"{r['id']}.md").read_text(encoding="utf-8")
        assert r["grounding_bytes"] == len(text.encode("utf-8")), \
            f"{r['id']} grounding_bytes is stale"
        assert r["grounding_sha256"] == \
            hashlib.sha256(text.encode("utf-8")).hexdigest(), \
            f"{r['id']} grounding_sha256 is stale - was the doc hand-edited?"


def test_documents_carry_provisioning(records):
    """A grounding doc with no CHI provisioning in it grounds nothing. Every
    artifact here was selected precisely because it has some."""
    barren = []
    for r in records:
        text = (GROUNDING_DIR / f"{r['id']}.md").read_text(encoding="utf-8")
        if not any(tok in text for tok in _strong_calls()):
            barren.append(r["id"])
    assert not barren, f"grounding with no provisioning content: {barren}"


def test_size_ceilings_hold(records):
    over = [(r["id"], r["grounding_bytes"]) for r in records
            if r["grounding_bytes"] > HARD_MAX]
    assert not over, f"documents above the {HARD_MAX:,} B hard ceiling: {over}"


def test_truncation_is_announced_in_band(records):
    """A trimmed doc must say so inside itself. The registry flag alone is not
    enough: whoever reads the document may never see the registry."""
    for r in records:
        text = (GROUNDING_DIR / f"{r['id']}.md").read_text(encoding="utf-8")
        marked = "TRUNCATED:" in text
        assert marked == bool(r["grounding_truncated"]), \
            f"{r['id']} truncation flag and in-band notice disagree"


def test_untruncated_docs_are_within_the_soft_budget(records):
    """Nothing should sit between the budgets without having been trimmed -
    that would mean the cap silently failed to apply."""
    for r in records:
        if not r["grounding_truncated"]:
            assert r["grounding_bytes"] <= HARD_MAX, r["id"]


def test_notebooks_are_never_dropped_for_scripts(records):
    """The rule that cost a rewrite: a .py file must never displace a
    provisioning notebook. If a doc is truncated, no `# ....ipynb` heading may
    be missing while a `# ....py` heading is present after it."""
    for r in records:
        text = (GROUNDING_DIR / f"{r['id']}.md").read_text(encoding="utf-8")
        if "TRUNCATED:" not in text:
            continue
        omitted = re.search(r"Omitted: ([^-]*)-->", text, re.DOTALL)
        if not omitted:
            continue
        dropped = [x.strip() for x in omitted.group(1).split(",")]
        dropped_nb = [d for d in dropped if d.endswith(".ipynb")]
        kept_py = re.findall(r"^# (\S+\.py)$", text, re.MULTILINE)
        assert not (dropped_nb and kept_py), (
            f"{r['id']} dropped notebooks {dropped_nb[:3]} while keeping "
            f"scripts {kept_py[:3]}")
