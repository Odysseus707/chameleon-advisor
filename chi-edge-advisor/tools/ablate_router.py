"""Router ablation: tree vs flat retrieval routing over the benchmark items.

For every benchmark item, run the prompt through the flat RetrievalRouter and
the hierarchical RouterTree, then score whether the item's source artifact
(``target_artifact``, mapped from benchmark A-ids to router artifact_ids)
lands in the top-k at each level:

  L0     tree picks the site the item asked for
  L1@k1  the target's use-case survives use-case soft routing (top-k1)
  L2@k2  the target artifact is among the selected artifacts (top-k2)
  chunk  at least one retrieved chunk comes from the target artifact

Items with no scoreable source — targets the registry does not carry (A4, the
bare-metal distractor, on the edge wing) or an empty ``target_artifact``
(designed no-source items) — are flagged ``covered=false`` and excluded from
the aggregates. An L0 with no site to check scores ``None`` and is excluded
from that level's denominator rather than counted as a miss.

Runs against either wing (``--wing``); see WINGS for the per-wing items
directory, id map and output stem. Emits Table A7 (tree vs flat) to
benchmark/exports/<stem>.{md,json}.

EXIT CODES: 0 measured something, 2 measured nothing. The second case is the
point — this tool spent its whole life defaulting --items at a directory that
had moved, finding zero items, printing "n/a" and exiting 0.

Usage (from chi-edge-advisor/):
    .venv/bin/python tools/ablate_router.py [--wing chameleon_bench]
        [--l1-k 2] [--l2-k 3] [--embedder hashing|auto]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))  # make `advisor` importable

import yaml  # noqa: E402

from advisor.artifacts.embeddings import HashingEmbedder, get_embedder  # noqa: E402
from advisor.artifacts.registry import ARTIFACTS_BY_ID  # noqa: E402
from advisor.artifacts.router import RetrievalRouter  # noqa: E402
from advisor.artifacts.store import ArtifactStore  # noqa: E402
from advisor.artifacts.tree import RouterTree  # noqa: E402

# benchmark artifact id -> router artifact_id (A4 is uncovered by design:
# a bare-metal/KVM@TACC distractor with no edge grounding in the registry).
A_TO_ROUTER = {
    "A1": "edge_ssh_image",
    "A2": "edge-picamera-image",
    "A3": "edge_sensehat_image",
    "A5": "serve-edge-chi",
    "A6": "edge-cpu-inference",
}

EXPECTED_SITE = "CHI@Edge"

# Per-wing wiring. The two wings key their artifacts differently and that is
# deliberate: the edge registry predates the corpus and uses repo slugs, while
# chameleon artifacts are keyed by their benchmark A-id so provenance keeps
# naming an id the benchmark can resolve. `id_map=None` means identity.
WINGS = {
    "chi_edge_bench": {
        "items": "chi_edge_bench/data/items",
        "id_map": A_TO_ROUTER,
        "site": EXPECTED_SITE,   # edge items carry no `site` field; all CHI@Edge
        "stem": "ablation_A7",
    },
    "chameleon_bench": {
        "items": "chameleon_bench/data/items",
        "id_map": None,          # A-ids ARE the registry keys for this wing
        "site": None,            # per-item `site`; unscored at L0 when absent
        "stem": "ablation_A7_chameleon",
    },
}


def load_items(items_dir: Path):
    items = []
    for path in sorted(items_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        items.append(
            {
                "id": data["id"],
                "prompt": data["prompt"],
                "targets": list(data.get("target_artifact") or []),
                "site": data.get("site"),
            }
        )
    return items


def score_item(item, flat, tree, id_map=None, expected_site=None):
    mapped = ([id_map[a] for a in item["targets"] if a in id_map] if id_map
              else list(item["targets"]))
    # A target the registry does not carry is not scoreable, and counting it as
    # a miss would blame the router for an artifact it was never given.
    mapped = [aid for aid in mapped if aid in ARTIFACTS_BY_ID]
    covered = bool(mapped)
    # L0 is only a claim when we know which site the item wanted.
    want_site = expected_site or item.get("site")
    target_ucs = {
        ARTIFACTS_BY_ID[aid].use_case or aid for aid in mapped if aid in ARTIFACTS_BY_ID
    }

    f = flat.route(item["prompt"])
    t = tree.route(item["prompt"])

    row = {
        "item": item["id"],
        "targets": item["targets"],
        "mapped": mapped,
        "covered": covered,
        "tree_site": t.site,
        "tree_status": t.status,
        "want_site": want_site,
        "tree": {
            "L0": None if not want_site else (t.status == "ok" and t.site == want_site),
            "L1": any(uc in t.selected_use_cases for uc in target_ucs),
            "L2": any(aid in t.selected_artifact_ids for aid in mapped),
            "chunk": any(c.artifact_id in mapped for c in t.chunks),
        },
        "flat": {
            "L2": any(aid in f.selected_artifact_ids for aid in mapped),
            "chunk": any(c.artifact_id in mapped for c in f.chunks),
        },
    }
    return row


def aggregate(rows):
    covered = [r for r in rows if r["covered"]]
    n = len(covered)

    def rate(getter):
        # None means "not a claim for this item" (an L0 with no declared site),
        # and it is excluded from the denominator rather than scored as a miss.
        vals = [v for v in (getter(r) for r in covered) if v is not None]
        return round(sum(1 for v in vals if v) / len(vals), 4) if vals else None

    return {
        "n_items": len(rows),
        "n_covered": n,
        "n_uncovered": len(rows) - n,
        "n_l0_scored": sum(1 for r in covered if r["tree"]["L0"] is not None),
        "tree": {
            "L0": rate(lambda r: r["tree"]["L0"]),
            "L1": rate(lambda r: r["tree"]["L1"]),
            "L2": rate(lambda r: r["tree"]["L2"]),
            "chunk": rate(lambda r: r["tree"]["chunk"]),
        },
        "flat": {
            "L2": rate(lambda r: r["flat"]["L2"]),
            "chunk": rate(lambda r: r["flat"]["chunk"]),
        },
    }


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _mark(b):
    if b is None:
        return "-"       # not a claim for this item, distinct from a miss
    return "Y" if b else "."


def render_markdown(config, agg, rows):
    lines = [
        "# Table A7: Router ablation — tree vs flat",
        "",
        f"*Generated {config['generated']} | embedder={config['embedder']} | "
        f"L1 top-k={config['l1_k']} | L2 top-k={config['l2_k']} | "
        f"budget={config['budget']} | items={agg['n_items']} "
        f"(covered {agg['n_covered']}, uncovered {agg['n_uncovered']})*",
        "",
        "Hit = the item's source artifact (`target_artifact`) lands in the top-k",
        "at that level. Aggregates are over covered items only; uncovered items",
        "(A4 targets — the bare-metal distractor with no router counterpart — and",
        "items with an empty `target_artifact`) are listed but not scored.",
        "",
        "## Aggregate hit rates",
        "",
        "| level | tree | flat |",
        "|---|---|---|",
        f"| L0 site | {_pct(agg['tree']['L0'])} | n/a (no site level) |",
        f"| L1 use-case @{config['l1_k']} | {_pct(agg['tree']['L1'])} | n/a (no use-case level) |",
        f"| L2 artifact @{config['l2_k']} | {_pct(agg['tree']['L2'])} | {_pct(agg['flat']['L2'])} |",
        f"| chunk-level | {_pct(agg['tree']['chunk'])} | {_pct(agg['flat']['chunk'])} |",
        "",
        "## Per-item results",
        "",
        "| item | target | covered | tree L0 | tree L1 | tree L2 | tree chunk | flat L2 | flat chunk |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        target = ",".join(r["targets"]) or "-"
        if r["covered"]:
            lines.append(
                f"| {r['item']} | {target} | yes "
                f"| {_mark(r['tree']['L0'])} | {_mark(r['tree']['L1'])} "
                f"| {_mark(r['tree']['L2'])} | {_mark(r['tree']['chunk'])} "
                f"| {_mark(r['flat']['L2'])} | {_mark(r['flat']['chunk'])} |"
            )
        else:
            lines.append(
                f"| {r['item']} | {target} | no (uncovered) | - | - | - | - | - | - |"
            )
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--wing", choices=sorted(WINGS), default="chi_edge_bench",
        help="which benchmark wing's items to score (default: the edge wing)",
    )
    ap.add_argument(
        "--items", default=None,
        help="override the wing's items directory",
    )
    ap.add_argument(
        "--out", default=str(_HERE.parent.parent / "benchmark" / "exports")
    )
    # 0 = no use-case truncation, which is RouterTree's own default and what
    # the pipeline runs. Forcing k=2 here for years hid that the gate COSTS
    # accuracy: on the edge suite it drops L2 from 93.5% to 78.5%, because
    # "peripherals" holds two artifacts and the gate discards the group.
    ap.add_argument("--l1-k", type=int, default=0, dest="l1_k",
                    help="use-case top-k (0 = no truncation, the default)")
    ap.add_argument("--l2-k", type=int, default=3, dest="l2_k")
    ap.add_argument("--budget", type=int, default=6)
    ap.add_argument(
        "--embedder",
        choices=["hashing", "auto"],
        default="hashing",
        help="hashing = deterministic offline (default); auto = bge if available",
    )
    args = ap.parse_args()

    embedder = HashingEmbedder() if args.embedder == "hashing" else get_embedder()
    store = ArtifactStore(embedder=embedder).build()
    flat = RetrievalRouter(store, total_budget=args.budget, max_artifacts=args.l2_k)
    tree = RouterTree(
        store,
        total_budget=args.budget,
        max_artifacts=args.l2_k,
        use_case_top_k=args.l1_k or None,
    )

    wing = WINGS[args.wing]
    items_dir = Path(args.items) if args.items else (
        _HERE.parent.parent / "benchmark" / wing["items"])
    if not items_dir.is_dir():
        print(f"ERROR: items directory does not exist: {items_dir}", file=sys.stderr)
        return 2

    items = load_items(items_dir)
    rows = [score_item(item, flat, tree,
                       id_map=wing["id_map"], expected_site=wing["site"])
            for item in items]
    agg = aggregate(rows)

    config = {
        "generated": date.today().isoformat(),
        "wing": args.wing,
        "embedder": embedder.name,
        "l1_k": args.l1_k,
        "l2_k": args.l2_k,
        "budget": args.budget,
        "items_dir": str(items_dir),
        "expected_site": wing["site"],
        "a_to_router": wing["id_map"],
    }

    # P5: an empty result set reads as a pass. This tool printed
    # "0 covered / 0 items ... n/a" and exited 0 for as long as its --items
    # default pointed at benchmark/items, a directory that moved. A routing
    # measurement with no scoreable item is not a measurement, and the whole
    # point of running it before and after a change is that it can disagree.
    #
    # Checked BEFORE the writes: a vacuous run that clobbers the previous
    # baseline on its way to failing has destroyed the number you were about
    # to compare against.
    if not agg["n_items"]:
        print(f"ERROR: no items found under {items_dir}", file=sys.stderr)
        return 2
    if not agg["n_covered"]:
        print(f"ERROR: {agg['n_items']} items, none with a target the registry "
              f"carries — nothing was measured. Check the {args.wing} id map.",
              file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{wing['stem']}.json"
    md_path = out_dir / f"{wing['stem']}.md"
    json_path.write_text(
        json.dumps({"config": config, "aggregates": agg, "items": rows}, indent=2)
    )
    md_path.write_text(render_markdown(config, agg, rows))

    print(f"Table A7 (tree vs flat) — {agg['n_covered']} covered / {agg['n_items']} items")
    print(f"  tree : L0 {_pct(agg['tree']['L0'])}  L1@{args.l1_k} {_pct(agg['tree']['L1'])}  "
          f"L2@{args.l2_k} {_pct(agg['tree']['L2'])}  chunk {_pct(agg['tree']['chunk'])}")
    print(f"  flat :               L2@{args.l2_k} {_pct(agg['flat']['L2'])}  "
          f"chunk {_pct(agg['flat']['chunk'])}")
    print(f"  wrote {json_path}")
    print(f"  wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
