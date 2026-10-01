"""The deterministic extraction tier must contain only re-derivable facts.

This file is what makes Step 5 auditable. The authored tier is allowed to
describe an artifact only in terms of things that already appear here, so if
these files can contain invented content the whole verification chain collapses.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BENCH = Path(__file__).resolve().parent.parent
WING = BENCH / "chameleon_bench" / "data"
ARTIFACTS_DIR = WING / "artifacts"
EXTRACTIONS_DIR = WING / "extractions"
MANIFEST = ARTIFACTS_DIR / "_manifest.yaml"

EXPECTED_COUNT = 90

#: Written by Step 5, and required to be empty until then.
AUTHORED = ("summary", "preconditions", "traps_illustrated", "not_covered",
            "memorization_probes", "uncertainties")

STAGES = {"site/auth", "lease", "server", "container", "image", "storage",
          "network", "exec", "teardown", "other"}


@pytest.fixture(scope="module")
def docs():
    if not EXTRACTIONS_DIR.is_dir() or not any(EXTRACTIONS_DIR.glob("A*.yaml")):
        pytest.skip("extractions not built (corpus_v2/tools/extract.py run)")
    ids = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["ids"]
    return [yaml.safe_load((EXTRACTIONS_DIR / f"{i}.yaml").read_text("utf-8"))
            for i in ids]


def test_one_extraction_per_artifact(docs):
    files = sorted(p.stem for p in EXTRACTIONS_DIR.glob("A*.yaml"))
    assert len(files) == EXPECTED_COUNT
    assert [d["artifact_id"] for d in docs] == \
        yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["ids"]


def test_every_extraction_names_its_commit(docs):
    for d in docs:
        assert re.fullmatch(r"[0-9a-f]{40}", d["commit_hash"] or ""), \
            f"{d['artifact_id']} has no valid commit_hash"


def test_commit_matches_the_registry_pin(docs):
    """An extraction taken from a different tree than the record pins would be
    evidence for a commit it never read."""
    for d in docs:
        rec = yaml.safe_load(
            (ARTIFACTS_DIR / f"{d['artifact_id']}.yaml").read_text("utf-8"))
        assert d["commit_hash"] == rec["pinned_sha"], \
            f"{d['artifact_id']} extraction and registry disagree on the commit"


def test_every_extraction_has_provisioning_stages(docs):
    barren = [d["artifact_id"] for d in docs if not d["workflow_stages"]]
    assert not barren, f"extractions with no workflow stage: {barren}"


def test_stage_vocabulary_is_closed(docs):
    """An unknown stage means the classifier invented a label, which would let
    item builders silently miss a whole category of setup."""
    seen = {s["stage"] for d in docs for s in d["workflow_stages"]}
    assert seen <= STAGES, f"unknown stages: {sorted(seen - STAGES)}"


def test_bare_metal_vocabulary_is_actually_exercised(docs):
    """The wing exists because bare metal differs from edge. If `server` and
    `lease` never appear, the stage extension was pointless and something is
    being classified as `other`."""
    seen = {s["stage"] for d in docs for s in d["workflow_stages"]}
    for required in ("server", "lease", "site/auth"):
        assert required in seen, f"no artifact produced a {required!r} stage"


def test_every_stage_cites_a_source(docs):
    """source_ref is what a grep-gate checks authored prose against."""
    for d in docs:
        for s in d["workflow_stages"]:
            assert s["source_ref"].strip(), \
                f"{d['artifact_id']} has a stage with no source_ref"
            assert s["verbatim_code"].strip(), \
                f"{d['artifact_id']} has a stage with no code"


def test_api_calls_are_well_formed(docs):
    for d in docs:
        for c in d["api_calls"]:
            assert c["function"], f"{d['artifact_id']} api_call with no function"
            assert c["source_ref"].strip()
            assert c["exact_kwargs_as_used"], \
                f"{d['artifact_id']}.{c['function']} has no kwargs record"


def test_magic_strings_have_a_kind(docs):
    allowed = {"node_type", "machine_type", "flavor", "image_ref", "port",
               "device_profile", "count", "site", "gpu"}
    for d in docs:
        for m in d["magic_strings"]:
            assert m["kind"] in allowed, \
                f"{d['artifact_id']} magic_string kind={m['kind']!r}"


def test_the_deterministic_tool_writes_no_prose():
    """Step 4 must never author. Tests the TOOL, not the files: once Step 5 has
    run, the files legitimately contain prose, so asserting emptiness there
    would fail for the wrong reason and would have to be deleted - taking the
    real invariant with it. The invariant is that extract.py cannot produce
    prose, and that stays checkable forever.
    """
    import sys
    sys.path.insert(0, str(BENCH / "corpus_v2" / "tools"))
    import extract
    rec = {"id": "A10", "artifact_id": "x", "repo_url": "u", "pinned_sha": "0" * 40}
    fields = extract.extract_one.__doc__ or ""
    src = (BENCH / "corpus_v2" / "tools" / "extract.py").read_text()
    for field in AUTHORED:
        marker = f'"{field}": '
        assert marker in src, f"extract.py no longer emits {field} at all"
        line = src.split(marker, 1)[1].split("\n", 1)[0]
        assert line.strip().rstrip(",") in ("None", "[]"), (
            f"extract.py initialises {field} to {line.strip()!r} - the "
            "deterministic tier must leave authored fields empty")


def test_authored_fields_are_absent_or_complete(docs):
    """A half-authored record is worse than an unauthored one: it reads as
    reviewed. If a summary exists, the rest of the authored tier must too."""
    for d in docs:
        if not d.get("summary"):
            continue
        missing = [f for f in AUTHORED
                   if f != "summary" and not d.get(f)]
        assert not missing, \
            f"{d['artifact_id']} has a summary but empty {missing}"


def test_verbatim_code_is_verbatim(docs):
    """Spot-check that code was not paraphrased: every stage's code must appear
    in the grounding document, which is rendered from the same commit."""
    checked = 0
    for d in docs[:25]:
        gp = WING / "grounding" / f"{d['artifact_id']}.md"
        if not gp.is_file():
            continue
        ground = gp.read_text(encoding="utf-8")
        for s in d["workflow_stages"][:3]:
            code = s["verbatim_code"]
            if "...truncated" in code:
                continue
            first = next((ln.strip() for ln in code.splitlines()
                          if ln.strip() and not ln.strip().startswith("#")), "")
            if len(first) > 12:
                checked += 1
                assert first in ground, (
                    f"{d['artifact_id']} stage code not found in its own "
                    f"grounding doc: {first[:60]!r}")
    assert checked > 20, "spot-check covered too little to mean anything"


def test_reextraction_preserves_the_authored_tier():
    """extract.py rewrites the file the authored prose lives in.

    Without an explicit carry-forward a routine re-extraction deletes every
    summary, trap and probe, and the loss is invisible because the file still
    looks complete - just with summary back to null. That happened: a
    verification pass wiped 22 authored records. Third instance of the same
    shape (select_wing vs pin, select_wing vs grounding, extract vs authored),
    so it is asserted rather than remembered.
    """
    import sys
    sys.path.insert(0, str(BENCH / "corpus_v2" / "tools"))
    import extract
    src = (BENCH / "corpus_v2" / "tools" / "extract.py").read_text()
    assert "_carry_authored_forward" in src, \
        "extract.py no longer preserves the authored tier"
    for field in AUTHORED:
        assert field in extract.AUTHORED_FIELDS, \
            f"{field} is not in extract.AUTHORED_FIELDS and will be wiped"
