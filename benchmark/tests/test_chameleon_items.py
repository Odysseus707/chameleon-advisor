"""The baremetal_core items, and the constraint that makes them measure anything.

Decision 7 is the reason most of this file exists. Six repo+commit pairs back 14
artifacts with byte-identical grounding, so "fed a different artifact" and "fed
different text" are not the same statement. If the held-out condition feeds
content-identical text, the specifics are simply PRESENT - specifics pass, and
the item reads as evidence that competence transferred when the model just read
the answer. That is a false positive in the project's own favour, which is the
worst direction for a bias to run, and it is invisible in every other check.
"""
import hashlib
import sys

import pytest
import yaml

from chi_edge_bench import paths
from chi_edge_bench.harness.runner import evaluate
from chi_edge_bench.harness.validate_golds import as_answer

sys.path.insert(0, str(paths.DATA.parent.parent / "corpus_v2" / "tools"))
import build_core_items as B  # noqa: E402

SUITE = "baremetal_core"


@pytest.fixture(scope="module")
def recs():
    return B.load_registry()


@pytest.fixture(scope="module")
def items():
    """baremetal_core only. B.load_items() already scopes to the suite; the
    assertion guards against that scoping ever silently matching nothing."""
    out = [d for _, d in B.load_items()]
    assert out, "no baremetal_core items on disk"
    assert all(i["suite"] == SUITE for i in out)
    return out


def test_the_wing_ships_items_at_all(items):
    """Guards the fixture itself: every test below is vacuous on an empty set,
    and a vacuous suite reads exactly like a passing one."""
    assert len(items) >= 8


def test_every_item_declares_the_suite(items):
    assert {i["suite"] for i in items} == {SUITE}


def test_every_referenced_artifact_exists(items, recs):
    for i in items:
        for a in i["target_artifact"] + sum(i["fed_sets"].values(), []):
            assert a in recs, f"{i['id']} names {a}, which is not in the registry"


# -- decision 7, rule 1 -----------------------------------------------------

def test_heldout_never_feeds_content_identical_text(items, recs):
    for i in items:
        tgroups = {recs[t]["content_group"] for t in i["target_artifact"]}
        for a in i["fed_sets"].get("heldout", []):
            assert recs[a]["content_group"] not in tgroups, (
                f"{i['id']}: heldout feeds {a}, byte-identical to target "
                f"{i['target_artifact']}. Specifics would be present, so a "
                "specifics pass would read as transfer.")


def test_heldout_sets_are_internally_distinct(items, recs):
    """Feeding A31 and A32 spends two slots on one body while fed_sets claims
    two artifacts - the condition is then weaker than it reports."""
    for i in items:
        groups = [recs[a]["content_group"] for a in i["fed_sets"].get("heldout", [])]
        assert len(groups) == len(set(groups)), \
            f"{i['id']}: heldout has content-identical duplicates"


def test_heldout_excludes_the_target_itself(items):
    for i in items:
        assert not (set(i["fed_sets"].get("heldout", [])) & set(i["target_artifact"]))


# -- decision 7, rule 2 -----------------------------------------------------

def test_at_most_one_item_per_content_group(items, recs):
    seen = {}
    for i in items:
        for t in i["target_artifact"]:
            g = recs[t]["content_group"]
            assert g not in seen, (
                f"{i['id']} and {seen[g]} both target content_group {g}; one "
                "body would be counted twice in every aggregate rate.")
            seen[g] = i["id"]


# -- provenance -------------------------------------------------------------

def test_prompt_sha256_matches_the_prompt(items):
    """Prompts are provenance-bound: editing one silently invalidates every
    answer already collected under it."""
    for i in items:
        assert i["prompt_sha256"] == \
            hashlib.sha256(i["prompt"].encode()).hexdigest(), \
            f"{i['id']}: prompt edited without re-running build_core_items"


def test_derived_fields_are_all_present(items):
    for i in items:
        for f in B.DERIVED_FIELDS:
            assert f in i, f"{i['id']} is missing derived field {f}"


# -- R2: the gold admission gate -------------------------------------------

def test_every_gold_passes_its_own_checkers(items):
    """D06 carried over: a failing gold is a defective ITEM, never a defective
    gold. This is the gate that decides admission."""
    for i in items:
        rep = evaluate(i, as_answer(i), None)
        failed = [r["check"] for r in rep["results"] if not r["passed"]]
        assert rep["all_passed"], f"{i['id']} gold fails: {failed}"


def test_specifics_tokens_are_actually_in_the_target_grounding(items, recs):
    """An item may not demand a specific its own target never supplied.

    This is what retargeting CB06 was about: A21's registry lists
    compute_cascadelake_r because rank.py merges signals across linked repos,
    but the literal is absent from the grounding document the model is fed. An
    item asserting it would be unanswerable from its own matched context.
    """
    paths.set_wing("chameleon_bench")
    try:
        for i in items:
            text = "\n".join(
                (paths.grounding_dir() / f"{a}.md").read_text()
                for a in i["fed_sets"]["matched"])
            for tok in i.get("key_tokens", {}).get("specifics", []):
                assert tok in text, (
                    f"{i['id']}: specifics token {tok!r} is absent from its own "
                    f"matched grounding {i['fed_sets']['matched']}")
    finally:
        paths.set_wing(None)


# -- the builder's gate, mutation-tested ------------------------------------

def test_violations_catches_a_content_identical_heldout(recs):
    a, b = "A31", "A32"                       # byte-identical grounding
    assert recs[a]["content_group"] == recs[b]["content_group"]
    item = {"id": "X", "suite": SUITE, "prompt": "p",
            "prompt_sha256": B.prompt_sha256("p"),
            "target_artifact": [a],
            "fed_sets": {"matched": [a], "heldout": [b]}}
    bad = B.violations([(None, item)], recs)
    assert any("byte-identical" in v for v in bad), bad


def test_violations_catches_two_items_on_one_content_group(recs):
    a, b = "A31", "A32"
    mk = lambda i, t: {"id": i, "suite": SUITE, "prompt": i,
                       "prompt_sha256": B.prompt_sha256(i),
                       "target_artifact": [t], "fed_sets": {"matched": [t]}}
    bad = B.violations([(None, mk("X", a)), (None, mk("Y", b))], recs)
    assert any("counted twice" in v for v in bad), bad


def test_violations_catches_an_edited_prompt(recs):
    item = {"id": "X", "suite": SUITE, "prompt": "edited after the fact",
            "prompt_sha256": B.prompt_sha256("the original"),
            "target_artifact": ["A7"], "fed_sets": {"matched": ["A7"]}}
    bad = B.violations([(None, item)], recs)
    assert any("prompt_sha256" in v for v in bad), bad


def test_violations_is_clean_on_the_real_items(recs):
    assert B.violations(B.load_items(), recs) == []


def test_heldout_for_never_selects_content_identical_pairs(recs):
    """Tests the GENERATOR, not just the items on disk.

    test_heldout_sets_are_internally_distinct reads what is already written, so
    it stays green when the selection logic breaks - only newly generated
    fed_sets would be wrong. Mutation-testing caught exactly that gap. Sweeping
    every artifact as a target exercises the paths where a duplicate pair
    genuinely is among the nearest neighbours (A17 originally drew A31+A32).
    """
    for target in recs:
        chosen = B.heldout_for({"key_tokens": {}}, [target], recs)
        groups = [recs[a]["content_group"] for a in chosen]
        assert len(groups) == len(set(groups)), \
            f"heldout_for({target}) returned content-identical {chosen}"
        assert recs[target]["content_group"] not in groups, \
            f"heldout_for({target}) returned a target-identical body"
        assert len(chosen) == B.HELDOUT_K, \
            f"heldout_for({target}) returned {len(chosen)}, want {B.HELDOUT_K}"


# -- the instrument itself --------------------------------------------------
# Two bugs found while building the pilot, both of which flattered us. They are
# the only errors here that produce a WRONG SCIENTIFIC CONCLUSION rather than a
# broken run, so they get their own tests.

def test_heldout_never_hands_over_the_specifics(items, recs):
    """Held-out feeding must leave the specifics absent.

    The prediction it exists to test is: transfer -> mechanism passes and
    specifics fail; lookup -> both fail. If the held-out artifacts name the
    node type or the image, specifics pass for a system that merely read them,
    and the item scores as evidence of transfer. Three of the first eight items
    had exactly this defect, because ranking neighbours by similarity selects
    the artifacts most likely to repeat the same literals.
    """
    paths.set_wing("chameleon_bench")
    try:
        for i in items:
            spec = i.get("key_tokens", {}).get("specifics") or []
            for a in i["fed_sets"].get("heldout", []):
                text = (paths.grounding_dir() / f"{a}.md").read_text()
                leaked = [t for t in spec if t in text]
                assert not leaked, (
                    f"{i['id']}: heldout artifact {a} names {leaked}; the "
                    "held-out condition contains the answer")
    finally:
        paths.set_wing(None)


def test_partial_is_a_strict_subset_and_provably_insufficient(items, recs):
    """A `partial` set that covers every key token is `matched` renamed, and an
    item built on it cannot demonstrate composition at all."""
    for i in items:
        part = i["fed_sets"].get("partial")
        if part is None:
            continue
        matched = set(i["fed_sets"]["matched"])
        assert part and set(part) < matched, \
            f"{i['id']}: partial {part} is not a strict subset of {sorted(matched)}"
        assert B.uncovered_tokens(i, part, recs), \
            f"{i['id']}: partial {part} already covers every key token"


def test_composition_items_declare_more_than_one_target(items):
    for i in items:
        if (i.get("tier_intent_by_condition") or {}).get("matched") == "T3":
            assert len(i["target_artifact"]) > 1, \
                f"{i['id']} intends T3 but names one artifact; T3 means no " \
                "single fed artifact covers the answer"
            assert "partial" in i["fed_sets"], \
                f"{i['id']} is a composition item with no partial condition"
