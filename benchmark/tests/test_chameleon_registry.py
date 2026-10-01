"""The chameleon wing's membership is a tracked, checkable fact.

artifacts/A*.yaml plus _manifest.yaml replace three gitignored derived files
(catalog.jsonl, manifest.tsv, the ranking workbook) as the answer to "which
artifacts is this wing made of". Those inputs are reproducible but absent from
a fresh clone, so the wing's membership was recorded nowhere durable.

One file per artifact, matching the edge wing's extractions/A1.yaml and
grounding/A1.md exactly. A single blob diffed terribly: every re-run touched
one file, so a one-artifact change was invisible in review.

The ids are load-bearing. Prompts are provenance-bound by sha256 of their text,
so an artifact changing id silently invalidates every answer collected against
items that cite it. These tests pin the properties that keep ids stable:
contiguous, alphabetically assigned, and disjoint from the edge wing's A1-A6.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BENCH = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = BENCH / "chameleon_bench" / "data" / "artifacts"
MANIFEST = ARTIFACTS_DIR / "_manifest.yaml"
ARTIFACT_GLOB = "A*.yaml"

FIRST_ID = 7
EXPECTED_COUNT = 90
EDGE_IDS = {f"A{i}" for i in range(1, 7)}
PIN_SOURCES = {"clone_head"}
PIN_STATUSES = {"pending", "verified", "verified_trovi_unreachable",
                "no_clone", "not_a_git_repo"}

REQUIRED_KEYS = {
    "id", "artifact_id", "trovi_title", "trovi_uuid", "contents_urn",
    "contents_kind", "repo_url", "repo_urls", "pinned_sha", "pin_source",
    "pin_status", "fetch_status", "tier", "advisor_rank", "advisor_score",
    "triage_class", "api_family", "python_chi_era", "site_call_style",
    "trovi_declared_sha", "pinned_utc", "pin_matches_trovi",
    "trovi_sha_present", "diverges_in_code", "divergent_files",
    "site_observed", "node_types_observed", "flavors_observed",
    "gpus_mentioned", "image_observed", "lease_hours_declared",
    "workload_tags", "resource_tags", "retrieval_tags",
    "record_type", "has_public_network",
    "grounding", "extraction",
}


@pytest.fixture(scope="module")
def reg():
    if not MANIFEST.is_file():
        pytest.skip("registry not built yet "
                    "(python corpus_v2/tools/select_wing.py run)")
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def artifacts(reg):
    """Records in MANIFEST order, not glob order.

    sorted() on these filenames gives A10 before A2. Every ordering assertion
    below would be meaningless against that, and any stage that reported or
    renumbered in glob order would be quietly wrong.
    """
    out = []
    for i in reg["ids"]:
        path = ARTIFACTS_DIR / f"{i}.yaml"
        assert path.is_file(), f"manifest names {i} but {path.name} is missing"
        out.append(yaml.safe_load(path.read_text(encoding="utf-8")))
    return out


def test_one_file_per_artifact():
    """Uniform with the edge wing: extractions/A1.yaml, grounding/A1.md, and
    now artifacts/A7.yaml - one artifact per file, never a single blob."""
    files = sorted(p.name for p in ARTIFACTS_DIR.glob(ARTIFACT_GLOB))
    assert len(files) == EXPECTED_COUNT, \
        f"expected {EXPECTED_COUNT} record files, found {len(files)}"
    assert not (ARTIFACTS_DIR / "registry.yaml").exists(), \
        "the monolithic registry.yaml is back; records must stay one-per-file"


def test_manifest_ids_match_the_files_on_disk(reg):
    """The manifest duplicates what a glob would tell you, so that a record
    file going missing is a mismatch rather than a silently smaller corpus."""
    on_disk = {p.stem for p in ARTIFACTS_DIR.glob(ARTIFACT_GLOB)}
    named = set(reg["ids"])
    assert named == on_disk, (
        f"manifest-but-absent: {sorted(named - on_disk)}; "
        f"present-but-unlisted: {sorted(on_disk - named)}")


def test_manifest_is_outside_the_artifact_glob():
    """_manifest.yaml must not be mistaken for a record, the same way
    capability_table.yaml sits outside items/."""
    assert MANIFEST.is_file()
    assert MANIFEST.name not in {p.name for p in
                                 ARTIFACTS_DIR.glob(ARTIFACT_GLOB)}


def test_expected_population(reg, artifacts):
    assert len(artifacts) == EXPECTED_COUNT
    assert reg["counts"]["selected"] == len(artifacts), \
        "counts block disagrees with the artifact list"


def test_ids_are_contiguous_and_continue_the_a_series(artifacts):
    ids = [a["id"] for a in artifacts]
    expected = [f"A{FIRST_ID + i}" for i in range(len(artifacts))]
    assert ids == expected, "ids must be contiguous A7..A97 in list order"


def test_ids_do_not_collide_with_the_edge_wing(artifacts):
    """A1-A6 are chi_edge_bench's. An overlap would make 'A3' ambiguous in any
    combined report."""
    clash = EDGE_IDS & {a["id"] for a in artifacts}
    assert not clash, f"ids collide with the edge wing: {sorted(clash)}"


def test_ids_are_assigned_alphabetically(artifacts):
    """The stability property. If ids were assigned by rank, re-running rank.py
    would renumber the corpus and invalidate every provenance-bound prompt."""
    slugs = [a["artifact_id"] for a in artifacts]
    assert slugs == sorted(slugs), \
        "artifact_id order is not alphabetical, so ids are not rank-stable"


def test_artifact_ids_are_unique(artifacts):
    slugs = [a["artifact_id"] for a in artifacts]
    assert len(set(slugs)) == len(slugs), "duplicate artifact_id in registry"


def test_every_record_has_the_full_schema(artifacts):
    for a in artifacts:
        missing = REQUIRED_KEYS - set(a)
        assert not missing, f"{a['id']} missing keys: {sorted(missing)}"


@pytest.mark.parametrize("field", ["site_observed", "node_types_observed",
                                   "workload_tags", "resource_tags",
                                   "retrieval_tags", "repo_urls"])
def test_list_fields_are_lists(artifacts, field):
    """These are consumed as lists by the advisor and the item builders; a
    '; '-joined string that slipped through would iterate as characters."""
    for a in artifacts:
        assert isinstance(a[field], list), \
            f"{a['id']}.{field} is {type(a[field]).__name__}, not a list"


SHA_RE = r"[0-9a-f]{40}"


def test_every_artifact_is_pinned(artifacts):
    """An unpinned record cannot be grounded or extracted reproducibly: it names
    no specific snapshot, so 'we used A7' means whatever that repo holds today."""
    unpinned = [a["id"] for a in artifacts if not a["pinned_sha"]]
    assert not unpinned, f"artifacts with no pinned commit: {unpinned}"


def test_pin_fields_are_well_formed(artifacts):
    for a in artifacts:
        assert a["pin_status"] in PIN_STATUSES, \
            f"{a['id']} has pin_status={a['pin_status']!r}"
        assert a["pin_source"] in PIN_SOURCES, \
            f"{a['id']} has pin_source={a['pin_source']!r}"
        for field in ("pinned_sha", "trovi_declared_sha"):
            sha = a[field]
            if sha is not None:
                assert re.fullmatch(SHA_RE, sha), \
                    f"{a['id']}.{field} is not a 40-hex sha: {sha!r}"


def test_pin_matches_trovi_agrees_with_the_two_shas(artifacts):
    """The flag is derived, so it must not contradict what it derives from.
    A stale `true` here would hide exactly the divergence it exists to record."""
    for a in artifacts:
        trovi, pinned, flag = (a["trovi_declared_sha"], a["pinned_sha"],
                               a["pin_matches_trovi"])
        if trovi is None:
            assert flag is None, \
                f"{a['id']} has no Trovi sha but pin_matches_trovi={flag!r}"
        else:
            assert flag == (pinned == trovi), \
                f"{a['id']} pin_matches_trovi={flag!r} but " \
                f"pinned={pinned!r} trovi={trovi!r}"


def test_divergence_is_recorded_not_guessed(artifacts):
    """Where the Trovi commit could not be obtained, divergence is UNKNOWN.
    Recording it as False would assert the trees agree without having looked."""
    for a in artifacts:
        if a["pin_status"] == "verified_trovi_unreachable":
            assert a["trovi_sha_present"] is False
            assert a["diverges_in_code"] is None, \
                f"{a['id']} claims to know divergence it could not measure"
        if a["diverges_in_code"] is None:
            assert a["divergent_files"] == [], \
                f"{a['id']} lists divergent files but divergence is unknown"


def test_matching_pins_do_not_diverge(artifacts):
    """Same sha means same tree, necessarily."""
    for a in artifacts:
        if a["pin_matches_trovi"] is True:
            assert a["diverges_in_code"] is False and not a["divergent_files"], \
                f"{a['id']} pins Trovi's own commit yet reports divergence"


def test_counts_block_matches_the_records(reg, artifacts):
    """The manifest counts describe what Trovi DECLARES, which after Step 2 is
    no longer the same question as what we pinned."""
    c = reg["counts"]
    declared = sum(1 for a in artifacts if a["trovi_declared_sha"])
    none = sum(1 for a in artifacts if not a["trovi_declared_sha"])
    assert c["trovi_declares_a_commit"] == declared
    assert c["no_trovi_commit"] == none
    assert declared + none == len(artifacts)


def test_no_edge_artifacts_survived_selection(artifacts):
    """The wing is bare-metal + KVM. An edge artifact here would be double
    counted against the edge wing, which already covers three of the four."""
    edge = [a["id"] for a in artifacts if a["api_family"] == "edge"]
    assert not edge, f"edge-family artifacts in the chameleon wing: {edge}"


def test_excluded_artifacts_are_recorded_with_reasons(reg):
    """Dropped artifacts are documented, not vanished - otherwise 'why is this
    not here' is unanswerable a year later."""
    excluded = reg["excluded"]
    assert len(excluded) == 5   # 4 edge-family + 1 compendium duplicate
    for e in excluded:
        assert e["status"] == "excluded"
        assert e["exclusion_reason"].strip(), \
            f"{e['artifact_id']} excluded without a reason"


def test_excluded_are_not_also_selected(reg, artifacts):
    selected = {a["artifact_id"] for a in artifacts}
    clash = selected & {e["artifact_id"] for e in reg["excluded"]}
    assert not clash, f"artifacts both selected and excluded: {sorted(clash)}"


def test_grounding_and_extraction_paths_match_ids(artifacts):
    """Steps 3 and 4 write to these paths; a mismatch silently orphans a file."""
    for a in artifacts:
        assert a["grounding"] == f"grounding/{a['id']}.md"
        assert a["extraction"] == f"extractions/{a['id']}.yaml"


def test_each_record_file_is_named_for_its_id(artifacts):
    """A7.yaml must contain A7. A copy-paste that left the wrong id inside
    would make the file silently describe another artifact."""
    for a in artifacts:
        path = ARTIFACTS_DIR / f"{a['id']}.yaml"
        assert path.is_file()
        assert a["id"] == path.stem, \
            f"{path.name} contains id={a['id']!r}"


RECORD_TYPES = {"reproducible-research", "teaching", "appliance", "example",
                "experiment"}


def test_record_type_is_a_closed_vocabulary(artifacts):
    """`reproducibility` and `teaching` were demoted out of workload_tags into
    this field because they describe what KIND of record an artifact is, not
    what workload it runs."""
    for a in artifacts:
        assert a["record_type"] in RECORD_TYPES, \
            f"{a['id']} record_type={a['record_type']!r}"


def test_no_workload_tag_dominates_the_corpus(artifacts):
    """A tag most of the corpus shares cannot route a query. Before the
    category-tag repair `reproducibility` was on 58% of artifacts; the ceiling
    here is what stops that recurring."""
    from collections import Counter
    c = Counter(t for a in artifacts for t in a["workload_tags"])
    n = len(artifacts)
    hogs = {t: f"{100 * v / n:.0f}%" for t, v in c.items() if v / n > 0.35}
    assert not hogs, f"workload tags on >35% of the corpus: {hogs}"


def test_demoted_tags_are_gone_from_workload_tags(artifacts):
    for a in artifacts:
        leaked = {"reproducibility", "teaching"} & set(a["workload_tags"])
        assert not leaked, f"{a['id']} still carries demoted tags {leaked}"
        assert "public-network" not in a["resource_tags"], \
            f"{a['id']} still carries public-network as a tag"


def test_sources_are_recorded_for_staleness_detection(reg):
    """The registry is derived from three gitignored files. Recording their
    hashes is what makes 'this registry was built from stale inputs'
    detectable rather than invisible."""
    src = reg["sources"]
    for key in ("catalog_jsonl_sha256", "manifest_tsv_sha256",
                "ranking_xlsx_sha256"):
        assert re.fullmatch(r"[0-9a-f]{64}", src[key]), \
            f"{key} is not a sha256: {src.get(key)!r}"


def test_downstream_fields_survive_a_selection_rerun(artifacts):
    """Four tools write these files; whichever runs last must not erase the rest.

    This has failed twice. First pin.py's fields were reset by a selection
    re-run; the fix listed only those, so the next re-run wiped grounding_* and
    extraction_* instead - visible only because the grounding tests began
    skipping rather than failing. The list is now asserted against the record
    itself so a new stage cannot be added without extending it.
    """
    import sys
    sys.path.insert(0, str(BENCH / "corpus_v2" / "tools"))
    from select_wing import DOWNSTREAM_OWNED_FIELDS

    populated = {k for a in artifacts for k, v in a.items()
                 if v not in (None, [], "pending")}
    stage_written = {
        "pinned_sha", "pin_source", "pin_status", "pinned_utc",
        "grounding_bytes", "grounding_sha256", "grounding_sections",
        "extraction_sha256", "extraction_calls",
    } & populated
    unguarded = stage_written - set(DOWNSTREAM_OWNED_FIELDS)
    assert not unguarded, (
        f"fields written by a later stage but not carried forward by "
        f"select_wing.py: {sorted(unguarded)} - a selection re-run will wipe them")


def test_later_stages_actually_populated_their_fields(artifacts):
    """Guards the failure mode that hid the last bug: fields silently reset to
    null make the downstream tests SKIP, which reads as green."""
    for field in ("pinned_sha", "grounding_bytes", "grounding_sha256",
                  "extraction_sha256"):
        missing = [a["id"] for a in artifacts if not a.get(field)]
        assert not missing, (
            f"{field} empty for {len(missing)} record(s) e.g. {missing[:5]} - "
            "run the corpus_v2 stages, or a re-run has wiped them")


def test_content_group_is_recorded_for_every_artifact(artifacts):
    """Six repo+commit pairs back 15 of the 91 artifacts, so their grounding is
    byte-identical. Without a recorded content identity nothing downstream can
    tell that A43 and A44 are the same text."""
    missing = [a["id"] for a in artifacts if not a.get("content_group")]
    assert not missing, f"content_group unset for {missing[:5]}"


def test_identical_grounding_implies_identical_content_group(artifacts):
    """The group must track the bytes, not the id.

    This is the guard for the held-out condition: an item that targets one
    artifact and feeds a same-group artifact as `heldout` is feeding the SAME
    text, which silently destroys the H0/H1 contrast the benchmark exists to
    measure. Part 2's item builder must refuse a same-group heldout, and it can
    only do that if this mapping is true.
    """
    import hashlib
    import re
    ground = BENCH / "chameleon_bench" / "data" / "grounding"
    by_body: dict[str, set] = {}
    for a in artifacts:
        text = (ground / f"{a['id']}.md").read_text(encoding="utf-8")
        body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        key = hashlib.sha256(body.encode()).hexdigest()[:12]
        by_body.setdefault(key, set()).add(a["content_group"])
    inconsistent = {k: v for k, v in by_body.items() if len(v) != 1}
    assert not inconsistent, \
        f"same grounding body mapped to different content_groups: {inconsistent}"


def test_no_phantom_node_types(artifacts):
    """`storage` is a real node type, an English word, and a python-chi module.

    Measured over this corpus the word wins 50 to 0: fifty artifacts listed it
    in node_types_observed and not one passed it to a reservation call. Left in,
    it would seed the advisor and Part 2's capability table with hardware
    nothing uses.
    """
    import sys
    sys.path.insert(0, str(BENCH / "corpus_v2" / "tools"))
    from select_wing import PHANTOM_NODE_TYPES
    bad = {a["id"]: sorted(set(a["node_types_observed"]) & PHANTOM_NODE_TYPES)
           for a in artifacts
           if set(a["node_types_observed"]) & PHANTOM_NODE_TYPES}
    assert not bad, f"phantom node types survived the repair: {bad}"


def test_the_pipeline_is_idempotent():
    """Re-running any stage on unchanged inputs must write nothing.

    Two stages stamped a timestamp unconditionally, so every re-run rewrote
    every record and failed the parity gate having changed nothing real. A gate
    that fails on a no-op run is a gate people learn to ignore - which is how
    the last one stayed broken for a month.
    """
    import subprocess
    import sys
    tools = BENCH / "corpus_v2" / "tools"
    for tool in ("select_wing", "pin", "render_grounding", "extract"):
        proc = subprocess.run([sys.executable, str(tools / f"{tool}.py"), "run"],
                              capture_output=True, text=True, cwd=BENCH)
        assert proc.returncode == 0, f"{tool} failed: {proc.stderr[-300:]}"
        out = proc.stdout
        # Match the COUNT, not a substring of it. The first version searched for
        # "0 record(s) updated", which is a substring of "90 record(s) updated" -
        # so the test passed vacuously for any count ending in zero, including a
        # tool rewriting every record. Anchor on a word boundary.
        wrote = re.findall(r"\b(\d+) (?:written|new/changed|record\(s\) updated)",
                           out)
        assert wrote, f"{tool}.py printed no write count:\n{out[-400:]}"
        nonzero = [n for n in wrote if n != "0"]
        assert not nonzero, (
            f"{tool}.py rewrote {nonzero} file(s) on a no-op run:\n{out[-400:]}")
