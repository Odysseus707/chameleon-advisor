"""Router ablation: tree vs flat retrieval routing over the benchmark_v4 items.

For every benchmark item, run the prompt through the flat RetrievalRouter and
the hierarchical RouterTree, then score whether the item's source artifact
(``target_artifact``, mapped from benchmark A-ids to router artifact_ids)
lands in the top-k at each level:

  L0     tree picks the correct site (all covered targets live on CHI@Edge)
  L1@k1  the target's use-case survives use-case soft routing (top-k1)
  L2@k2  the target artifact is among the selected artifacts (top-k2)
  chunk  at least one retrieved chunk comes from the target artifact

Items with no scoreable source — targets with no router counterpart (A4, the
bare-metal distractor) or an empty ``target_artifact`` (designed no-source
items) — are flagged ``covered=false`` and excluded from the aggregates.

Emits Table A7 (tree vs flat) to benchmark_v4/exports/ablation_A7.{md,json}.

Usage (from chi-edge-advisor/):
    .venv/bin/python tools/ablate_router.py [--l1-k 2] [--l2-k 3] [--embedder hashing|auto]
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


def load_items(items_dir: Path):
    items = []
    for path in sorted(items_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        items.append(
            {
                "id": data["id"],
                "prompt": data["prompt"],
                "targets": list(data.get("target_artifact") or []),
            }
        )
    return items


def score_item(item, flat, tree):
    mapped = [A_TO_ROUTER[a] for a in item["targets"] if a in A_TO_ROUTER]
    covered = bool(mapped)
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
        "tree": {
            "L0": t.status == "ok" and t.site == EXPECTED_SITE,
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
        return round(sum(1 for r in covered if getter(r)) / n, 4) if n else None

    return {
        "n_items": len(rows),
        "n_covered": n,
        "n_uncovered": len(rows) - n,
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
        "--items", default=str(_HERE.parent.parent / "benchmark_v4" / "items")
    )
    ap.add_argument(
        "--out", default=str(_HERE.parent.parent / "benchmark_v4" / "exports")
    )
    ap.add_argument("--l1-k", type=int, default=2, dest="l1_k")
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
        use_case_top_k=args.l1_k,
    )

    items = load_items(Path(args.items))
    rows = [score_item(item, flat, tree) for item in items]
    agg = aggregate(rows)

    config = {
        "generated": date.today().isoformat(),
        "embedder": embedder.name,
        "l1_k": args.l1_k,
        "l2_k": args.l2_k,
        "budget": args.budget,
        "items_dir": args.items,
        "expected_site": EXPECTED_SITE,
        "a_to_router": A_TO_ROUTER,
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "ablation_A7.json"
    md_path = out_dir / "ablation_A7.md"
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


if __name__ == "__main__":
    main()
