"""select_wing: freeze the chameleon wing's artifact membership. Stage 4.

The 91 artifacts of the general (bare-metal + KVM) wing are already chosen -
they are the code-bearing ones - but that choice lives only in derived files
that are all gitignored: catalog.jsonl, manifest.tsv and the ranking workbook.
Nothing tracked says which artifacts the wing is made of, and the clones sit at
whatever HEAD they happened to be at when fetch.py ran.

This writes the tracked answer:

    chameleon_bench/data/artifacts/registry.yaml

which becomes the single source of truth for the wing's membership - consumed by
pin.py, render_grounding.py, extract.py, and (Part 2) by the advisor's own
artifact registry, so the benchmark and the advisor cannot drift apart.

SELECTION RULE
    tier in {A, B, C}  minus the four CHI@Edge-family artifacts

Tier A/B/C is exactly the set with `triage_class in {instructional, evidence}`,
i.e. artifacts carrying real Chameleon provisioning code. That equivalence is
asserted, not assumed: if the workbook and the manifest ever disagree, one of
them is stale and this refuses to run rather than silently picking one.

The edge four are dropped because three of them ARE A1/A2/A3 in the edge wing
and the fourth is edge-only. Keeping them would give three artifacts two ids
across two wings and double-count them in any combined report. They are written
to the registry as `status: excluded` with a reason rather than vanishing.

IDS
    A7 .. A97, assigned alphabetically by artifact_id.

Continuing the A-series (A1-A6 are the edge wing's) and ordering alphabetically
rather than by rank: prompts are provenance-bound by sha256, so a renumber
invalidates collected answers. Alphabetical order is stable against re-ranking
and re-triage. Tier and rank are recorded as fields instead.

  python corpus_v2/tools/select_wing.py run
  python corpus_v2/tools/select_wing.py run --dry-run   # print the plan only

NAME. Not `select.py`: the tools directory goes on sys.path ahead of the
stdlib, and `subprocess` imports `select`. A module named select.py here
shadows it and breaks every sibling that shells out.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import load_catalog          # noqa: E402
from triage import load_manifest          # noqa: E402

CORPUS = HERE.parent
BENCH = CORPUS.parent
WORKSPACE = BENCH.parent
RANKING = BENCH / "compendium" / "advisor_artifact_ranking.xlsx"
WING = BENCH / "chameleon_bench" / "data"

# One file per artifact, matching the edge wing exactly: extractions/A1.yaml,
# grounding/A1.md. A single 5000-line registry read fine and diffed terribly -
# every re-run touched one blob, so a one-artifact change was invisible in the
# diff and the parity gate could only say "the registry moved".
ARTIFACTS_DIR = WING / "artifacts"
MANIFEST = ARTIFACTS_DIR / "_manifest.yaml"

#: Per-artifact files are A*.yaml; the manifest is deliberately outside that
#: glob, the same way capability_table.yaml sits outside items/.
ARTIFACT_GLOB = "A*.yaml"

#: Fields written by LATER STAGES, not by this tool.
#:
#: Four tools now write the same A*.yaml files - select_wing, pin,
#: render_grounding and extract - so ownership has to be explicit or whichever
#: runs last silently erases the others' work. This list was originally only
#: the pin fields, and the omission bit immediately: re-running selection for
#: the tag repair wiped every grounding_* and extraction_* field, which
#: surfaced only because the grounding tests started skipping. Anything a later
#: stage writes belongs here.
DOWNSTREAM_OWNED_FIELDS = [
    # pin.py (Step 2)
    "pinned_sha", "pin_source", "pin_status", "pinned_utc",
    "pin_matches_trovi", "trovi_sha_present",
    "diverges_in_code", "divergent_files",
    # render_grounding.py (Step 3)
    "grounding_bytes", "grounding_sha256", "grounding_truncated",
    "grounding_sections", "content_group",
    # extract.py (Step 4)
    "extraction_sha256", "extraction_calls",
    # Step 5 authored pass
    "retrieval_tags",
]

#: What a record looks like before any later stage has touched it.
DOWNSTREAM_DEFAULTS = {
    "pinned_sha": None,
    "pin_source": None,
    "pin_status": "pending",
    "pinned_utc": None,
    "pin_matches_trovi": None,
    "trovi_sha_present": None,
    "diverges_in_code": None,
    "divergent_files": [],
    "content_group": None,
    "grounding_bytes": None,
    "grounding_sha256": None,
    "grounding_truncated": None,
    "grounding_sections": None,
    "extraction_sha256": None,
    "extraction_calls": None,
}

FIRST_ID = 7                      # A1-A6 belong to the edge wing
BEARING = {"instructional", "evidence"}
SELECTED_TIERS = {"A", "B", "C"}

#: Compendium transcription duplicates: the SAME Trovi record listed twice.
#:
#: `MPI+Spack Bare Metal Cluster` appears twice in compendium.txt, so catalog.py
#: deduplicated the slug by appending `-2` and produced two artifacts sharing one
#: trovi_uuid (cb35a375). Every substantive field matches. This is a counting
#: error, not a second artifact, and unlike the genuine variant pairs
#: (A100 vs H100, AMD vs NVIDIA) nothing is lost by removing it.
DUPLICATE_EXCLUSIONS = {
    "mpi-spack-bare-metal-cluster-2":
        "duplicate compendium entry: same trovi_uuid cb35a375 and title as "
        "mpi-spack-bare-metal-cluster; the compendium lists it twice",
}


#: The CHI@Edge-family artifacts, dropped so no artifact lives in both wings.
EDGE_EXCLUSIONS = {
    "ssh-on-chi-edge-tutorial":
        "already A1 in the edge wing (ChameleonCloud/edge_ssh_image)",
    "chi-edge-camera-peripheral-tutorial":
        "already A2 in the edge wing (ChameleonCloud/edge-picamera-image)",
    "chi-edge-sensors-and-gpio-tutorial":
        "already A3 in the edge wing (ChameleonCloud/edge_sensehat_image)",
    "floto-development-set-up":
        "CHI@Edge-only (UChicago-FLOTO/chi_edge_demo); out of scope for the "
        "bare-metal wing",
}

# ------------------------------------------------------- category-tag repair
#
# rank.py's workload vocabulary was built to SCORE artifacts, and it is not
# usable for retrieval as-is. Measured over the 91:
#
#   reproducibility  53/91 (58%)      teaching 28/91 (31%)
#   public-network   85/91 (93%)
#
# A tag most of the corpus shares cannot route a query. Worse, `reproducibility`
# and `teaching` are not workloads at all - they say what KIND OF RECORD an
# artifact is, which is a different axis and belongs in its own field.
#
# So they are demoted to `record_type`, and `public-network` becomes the plain
# boolean it always was. This is applied HERE rather than by re-running rank.py,
# deliberately: rank.py's tags feed advisor_score, which sets the A/B/C tier,
# which decides WHICH 91 ARTIFACTS ARE IN THE WING. Re-scoring to fix tag
# quality would silently change the corpus. The reviewed tiers stay untouched
# and only the tag fields are repaired.
#
# The cost is stated plainly: demotion takes artifacts with no workload tag from
# 7 to 36 of 91. That is not a regression introduced here - it is the true
# coverage of the vocabulary once the two near-universal tags stop masking it.
# Those 36 are filled by the Step 5 authored pass, which is also where the
# retrieval_tags - the words a user would actually type - come from.
DEMOTED_TO_RECORD_TYPE = {
    "reproducibility": "reproducible-research",
    "teaching": "teaching",
}

#: >80% prevalence. Kept as a fact, removed from the tag set it polluted.
DEMOTED_TO_FACT = {"public-network": "has_public_network"}


def repair_tags(workload: list[str], resource: list[str], trovi: list[str]):
    """(workload_tags, resource_tags, record_type, has_public_network)."""
    record_type = None
    for tag, name in DEMOTED_TO_RECORD_TYPE.items():
        if tag in workload:
            record_type = name
            break
    if record_type is None:
        low = {t.lower() for t in trovi}
        if "appliance" in low:
            record_type = "appliance"
        elif {"example", "experiment pattern"} & low:
            record_type = "example"
        else:
            record_type = "experiment"
    return (
        [t for t in workload if t not in DEMOTED_TO_RECORD_TYPE],
        [t for t in resource if t not in DEMOTED_TO_FACT],
        record_type,
        "public-network" in resource,
    )


#: Node-type tokens that the vocabulary sweep produces but that no artifact
#: actually reserves. Measured: 50 of 91 artifacts list `storage` as a node
#: type and ZERO pass it to a reservation call - every occurrence traces to
#: `from chi import storage`, "object storage" or "storage network". Left in, it
#: would put a node type that nothing uses into the advisor's recommendations
#: and into Part 2's capability table. Repaired here rather than in rank.py, for
#: the same reason as the tags: rank.py's output feeds the reviewed tiers.
PHANTOM_NODE_TYPES = {"storage"}


#: Workbook columns that hold "; "-joined lists.
LIST_COLUMNS = ["site_observed", "node_types_observed", "flavors_observed",
                "gpus_mentioned", "image_observed", "workload_tags",
                "resource_tags", "trovi_tags"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def split_list(value) -> list[str]:
    if value is None or value == "":
        return []
    return [p.strip() for p in str(value).split(";") if p.strip()]


def split_floats(value) -> list[float]:
    out = []
    for p in split_list(value):
        try:
            out.append(float(p))
        except ValueError:
            continue
    return out


def load_ranking() -> dict[str, dict]:
    """{artifact_id: row} from the 'Ranked Artifacts' sheet.

    The workbook is the REVIEWED artifact: its tiers and tags are what a human
    looked at. Recomputing them here from the clones would be reproducible but
    would risk silently differing from what was reviewed, so it is read rather
    than recalculated - and its sha256 goes into the registry header so a stale
    workbook is detectable later.
    """
    try:
        import openpyxl
    except ImportError:
        raise SystemExit(
            "openpyxl is required to read the ranking workbook.\n"
            "  pip install 'chi-edge-bench[xlsx]'   (or: pip install openpyxl)")
    if not RANKING.exists():
        raise SystemExit(
            f"{RANKING.relative_to(WORKSPACE)} missing. Run: "
            "python corpus_v2/tools/rank.py run")
    wb = openpyxl.load_workbook(RANKING, read_only=True, data_only=True)
    if "Ranked Artifacts" not in wb.sheetnames:
        raise SystemExit(
            f"'Ranked Artifacts' sheet missing from {RANKING.name}; "
            f"found {wb.sheetnames}")
    rows = list(wb["Ranked Artifacts"].iter_rows(values_only=True))
    wb.close()
    header = list(rows[0])
    out = {}
    for r in rows[1:]:
        d = dict(zip(header, r))
        if d.get("artifact_id"):
            out[str(d["artifact_id"])] = d
    return out


def cross_check(ranking: dict[str, dict], manifest: dict[str, dict]) -> None:
    """Tier A/B/C must equal the code-bearing set. Disagreement means one input
    is stale, and guessing which would silently change what the wing IS."""
    by_tier = {a for a, r in ranking.items()
               if str(r.get("tier") or "") in SELECTED_TIERS}
    by_class = {a for a, m in manifest.items() if m["triage_class"] in BEARING}
    if by_tier != by_class:
        only_tier = sorted(by_tier - by_class)
        only_class = sorted(by_class - by_tier)
        raise SystemExit(
            "ranking workbook and manifest.tsv disagree about which artifacts "
            "are code-bearing, so one of them is stale.\n"
            f"  tier A/B/C but not instructional/evidence: {only_tier}\n"
            f"  instructional/evidence but not tier A/B/C: {only_class}\n"
            "Re-run triage.py then rank.py, or investigate, before selecting.")


def build_records(catalog, manifest, ranking):
    """(selected records, excluded records). Ids assigned alphabetically."""
    chosen = sorted(a for a, r in ranking.items()
                    if str(r.get("tier") or "") in SELECTED_TIERS
                    and a not in EDGE_EXCLUSIONS
                    and a not in DUPLICATE_EXCLUSIONS)
    selected = []
    for i, aid in enumerate(chosen):
        cat, man, rank = catalog[aid], manifest[aid], ranking[aid]
        lists = {c: split_list(rank.get(c)) for c in LIST_COLUMNS}
        _tags = repair_tags(lists["workload_tags"], lists["resource_tags"],
                            lists["trovi_tags"])
        selected.append({
            "id": f"A{FIRST_ID + i}",
            "artifact_id": aid,
            "trovi_title": man.get("trovi_title") or cat.get("trovi_title") or "",
            "trovi_uuid": cat.get("trovi_uuid") or None,
            # -- provenance -------------------------------------------------
            "contents_urn": cat.get("contents_urn") or None,
            "contents_kind": cat.get("contents_kind") or None,
            "repo_url": man["repo_url"],
            "repo_urls": list(cat.get("repo_urls") or []),
            "fetch_status": man["fetch_status"],
            # What Trovi's contents URN names, which is NOT necessarily the
            # commit we use - see pin.py. Ours because it comes from the
            # catalog; everything else pin-related belongs to pin.py.
            "trovi_declared_sha": cat.get("contents_sha") or None,
            # Placeholders, carried forward on regeneration (PIN_OWNED_FIELDS).
            **DOWNSTREAM_DEFAULTS,
            # -- ranking, recorded not encoded ------------------------------
            "tier": str(rank.get("tier") or ""),
            "advisor_rank": int(rank.get("rank") or 0),
            "advisor_score": float(rank.get("advisor_score") or 0),
            "why_ranked": str(rank.get("why_ranked") or ""),
            "access_count": int(rank.get("access_count") or 0),
            # -- triage facts -----------------------------------------------
            "triage_class": man["triage_class"],
            "api_family": man["api_family_detected"],
            "python_chi_era": man["python_chi_era"],
            "site_call_style": man["site_call_style"],
            "n_provisioning_cells": int(man.get("n_provisioning_cells") or 0),
            "provisioning_density": float(man.get("provisioning_density") or 0),
            "dispersed": man.get("dispersed") == "True",
            # -- HARDWARE FACTS: what this artifact ran on. The answer side.
            #    Exact strings from the code; used as filters, never fuzzy-matched.
            "site_observed": lists["site_observed"],
            "node_types_observed": [n for n in lists["node_types_observed"]
                                    if n not in PHANTOM_NODE_TYPES],
            "flavors_observed": lists["flavors_observed"],
            "gpus_mentioned": lists["gpus_mentioned"],
            "image_observed": lists["image_observed"],
            "lease_hours_declared": split_floats(rank.get("lease_hours_declared")),
            # -- CATEGORY LABELS: for counting, grouping and stratified
            #    sampling. Not for matching a user's words (see repair_tags).
            "record_type": _tags[2],
            "workload_tags": _tags[0],
            "resource_tags": _tags[1],
            "has_public_network": _tags[3],
            "trovi_tags": lists["trovi_tags"],
            # -- SEARCH WORDS: what a user would actually type. This is what
            #    advisor.classify() matches against. Filled by Step 5.
            "retrieval_tags": [],
            # -- artefact paths, written by Steps 3 and 4 -------------------
            "grounding": f"grounding/A{FIRST_ID + i}.md",
            "extraction": f"extractions/A{FIRST_ID + i}.yaml",
        })
    excluded = [{
        "artifact_id": aid,
        "trovi_title": (manifest.get(aid) or {}).get("trovi_title", ""),
        "status": "excluded",
        "exclusion_reason": reason,
    } for aid, reason in sorted({**EDGE_EXCLUSIONS,
                                 **DUPLICATE_EXCLUSIONS}.items())]
    return selected, excluded


def _dump(doc) -> str:
    import yaml
    return yaml.safe_dump(doc, sort_keys=False, default_flow_style=False,
                          allow_unicode=True, width=100)


def render_artifact(rec: dict) -> str:
    """One artifact, one file - the same shape as extractions/A1.yaml."""
    header = f"""\
# {rec['id']} - {rec['artifact_id']}
#
# GENERATED by corpus_v2/tools/select_wing.py. Do not hand-edit: rerun the tool.
# Registry record for one artifact of the chameleon (bare-metal + KVM) wing.
# Companion files: {rec['grounding']}, {rec['extraction']}.
#
# The id is assigned ALPHABETICALLY by artifact_id and never moves: prompts are
# provenance-bound by sha256, so renumbering would invalidate every collected
# answer citing this artifact. Tier and rank are fields, not part of the id.
#
# `pinned_sha` is the commit Trovi's contents URN names, or null when the
# artifact has no git URN; pin.py resolves it against the clone and flips
# `pin_status` from pending to verified. `retrieval_tags` is filled by the
# Step 5 authored pass.
"""
    return header + _dump(rec)


def render_manifest(selected, excluded, sources) -> str:
    """Corpus-level facts that belong to no single artifact.

    Kept out of the per-artifact files so those stay purely about their
    artifact, and out of the A*.yaml glob so it is never mistaken for one -
    the same separation capability_table.yaml has from items/.
    """
    last = FIRST_ID + len(selected) - 1
    header = f"""\
# chameleon_bench artifact registry - manifest for the general (bare-metal +
# KVM) wing. The records themselves are one-per-file: {ARTIFACT_GLOB}.
#
# GENERATED by corpus_v2/tools/select_wing.py. Do not hand-edit: rerun the tool.
#
# Selection: ranking tier A/B/C (== triage_class instructional/evidence),
# minus the four CHI@Edge-family artifacts listed under `excluded`.
# Ids are A{FIRST_ID}..A{last}, assigned alphabetically by artifact_id.
#
# `ids` duplicates what globbing the directory would tell you. That is the
# point: a record file going missing is then a mismatch rather than a silently
# smaller corpus.
"""
    doc = {
        "version": "1.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wing": "chameleon",
        "sites": ["CHI@UC", "CHI@TACC", "KVM@TACC"],
        "counts": {
            "selected": len(selected),
            "excluded": len(excluded),
            # What Trovi DECLARES, which since Step 2 is a different question
            # from what we pinned - pin.py pins the clone, not Trovi's commit.
            # Naming these after the pin would have re-introduced that
            # confusion in the one file people read first.
            "trovi_declares_a_commit": sum(
                1 for r in selected if r.get("trovi_declared_sha")),
            "no_trovi_commit": sum(
                1 for r in selected if not r.get("trovi_declared_sha")),
        },
        # Recorded so a registry built from stale inputs is detectable.
        "sources": sources,
        "ids": [r["id"] for r in selected],
        "excluded": excluded,
    }
    return header + _dump(doc)


def _carry_pins_forward(path: Path, rec: dict) -> bool:
    """Copy every later stage's fields out of an existing record into the fresh one.

    Without this, re-running selection resets those fields and quietly discards
    Steps 2-5. It has already happened once: the list covered only the pin
    fields, so the tag repair silently wiped grounding_* and extraction_*
    across all 91 records.

    Returns True if anything was carried over.
    """
    if not path.exists():
        return False
    import yaml
    old = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    carried = False
    for key in DOWNSTREAM_OWNED_FIELDS:
        if key in old and old[key] != DOWNSTREAM_DEFAULTS.get(key):
            rec[key] = old[key]
            carried = True
    return carried


def _strip_timestamp(text: str) -> str:
    return "\n".join(l for l in text.splitlines()
                     if not l.startswith("generated_utc:"))


def _same_but_for_timestamp(old: str, new: str) -> bool:
    """Is a rewrite pure churn?

    The registry is fully reproducible from its inputs except for
    `generated_utc`. Rewriting it on every run would therefore change its
    sha256 with no change in content, and the parity gate would report
    `content modified` every time - a gate that cries wolf is a gate people
    learn to ignore, which is how the last one stayed broken for a month.
    So the timestamp is bumped only when something real changed.
    """
    return _strip_timestamp(old) == _strip_timestamp(new)


def run(dry_run: bool) -> int:
    catalog = {a["artifact_id"]: a for a in load_catalog()}
    manifest = {m["artifact_id"]: m for m in load_manifest()}
    ranking = load_ranking()

    missing = [a for a in ranking if a not in catalog or a not in manifest]
    if missing:
        raise SystemExit("ranking names artifacts absent from catalog/manifest: "
                         f"{missing[:5]}")
    cross_check(ranking, manifest)

    selected, excluded = build_records(catalog, manifest, ranking)
    sources = {
        "catalog_jsonl_sha256": sha256_file(CORPUS / "catalog.jsonl"),
        "manifest_tsv_sha256": sha256_file(CORPUS / "manifest.tsv"),
        "ranking_xlsx_sha256": sha256_file(RANKING),
    }

    print(f"[select] {len(selected)} artifacts -> "
          f"{selected[0]['id']}..{selected[-1]['id']}")
    for label, key in (("tier", "tier"), ("api_family", "api_family"),
                       ("python_chi_era", "python_chi_era"),
                       ("pin_source", "pin_source")):
        tally: dict[str, int] = {}
        for r in selected:
            tally[str(r[key])] = tally.get(str(r[key]), 0) + 1
        print(f"  {label:16} " + "  ".join(f"{k}={v}" for k, v in
                                           sorted(tally.items())))
    print(f"  excluded         {len(excluded)}: "
          f"{', '.join(e['artifact_id'][:30] for e in excluded)}")

    if dry_run:
        print("\n[dry-run] nothing written")
        for r in selected[:5]:
            print(f"    {r['id']:<5} {r['tier']} {r['artifact_id'][:52]}")
        print("    ...")
        for r in selected[-3:]:
            print(f"    {r['id']:<5} {r['tier']} {r['artifact_id'][:52]}")
        return 0

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    wrote, unchanged, kept_pins = [], 0, 0
    for rec in selected:
        path = ARTIFACTS_DIR / f"{rec['id']}.yaml"
        if _carry_pins_forward(path, rec):
            kept_pins += 1
        text = render_artifact(rec)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            unchanged += 1
            continue
        path.write_text(text, encoding="utf-8")
        wrote.append(rec["id"])

    # Record files whose artifact is no longer selected. Left in place rather
    # than deleted - an id vanishing is a decision, not a side effect - but
    # named loudly so it cannot pass unnoticed.
    keep = {f"{r['id']}.yaml" for r in selected}
    orphans = sorted(p.name for p in ARTIFACTS_DIR.glob(ARTIFACT_GLOB)
                     if p.name not in keep)

    man = render_manifest(selected, excluded, sources)
    man_changed = not (MANIFEST.exists() and _same_but_for_timestamp(
        MANIFEST.read_text(encoding="utf-8"), man))
    if man_changed:
        MANIFEST.write_text(man, encoding="utf-8")

    if kept_pins:
        print(f"  pins preserved   {kept_pins} record(s) kept their pin fields")
    print(f"\n[artifacts] {len(wrote)} written, {unchanged} unchanged "
          f"-> {ARTIFACTS_DIR.relative_to(WORKSPACE)}/{ARTIFACT_GLOB}")
    if wrote and len(wrote) <= 8:
        print(f"            {', '.join(wrote)}")
    print(f"[manifest]  {'written' if man_changed else 'unchanged'} "
          f"-> {MANIFEST.relative_to(WORKSPACE)}")
    if orphans:
        print(f"\n  WARNING: {len(orphans)} record file(s) no longer selected, "
              f"left on disk: {', '.join(orphans)}")
        print("  Remove them deliberately, or re-check the selection rule.")
    return 0


def load_registry() -> dict:
    """The whole wing as one dict, reassembled from the per-artifact files.

    Returns the manifest with an `artifacts` list spliced in, so every later
    stage (pin.py, render_grounding.py, extract.py, the advisor loader) sees a
    single object and does not care that it is stored one-file-per-artifact.

    Records are ordered by the manifest's `ids`, not by glob order: sorted()
    would give A10 before A2, and a stage that renumbers or reports in that
    order would be quietly wrong.
    """
    import yaml
    if not MANIFEST.exists():
        raise SystemExit("artifacts/_manifest.yaml missing. Run: "
                         "python corpus_v2/tools/select_wing.py run")
    doc = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    on_disk = {p.stem: p for p in ARTIFACTS_DIR.glob(ARTIFACT_GLOB)}
    missing = [i for i in doc["ids"] if i not in on_disk]
    extra = sorted(set(on_disk) - set(doc["ids"]))
    if missing or extra:
        raise SystemExit(
            "artifact record files disagree with the manifest.\n"
            f"  named in the manifest but absent: {missing}\n"
            f"  present but not in the manifest:  {extra}\n"
            "Re-run select_wing.py, or work out which is wrong first.")

    doc["artifacts"] = [
        yaml.safe_load(on_disk[i].read_text(encoding="utf-8")) for i in doc["ids"]
    ]
    return doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--dry-run", action="store_true",
                    help="print the selection without writing the registry")
    args = ap.parse_args()
    return run(args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
