#!/usr/bin/env python3
"""score_wing: score a collected arm on any wing, and compare arms.

WHY THIS IS NOT score_runs.py. That tool takes --suite {core,reservation} -
edge suites, by name - and it sits on the frozen measurement surface: the
parity gate re-scores all 3231 collected answers through it and byte-diffs the
result. Teaching it a second wing means editing the one thing whose output must
not change. This drives the same `harness.runner.evaluate` it does, from
outside that surface, so a chameleon arm can be scored without putting the edge
numbers at risk.

Both refuse a vacuous run. "0 items scored" with exit 0 is not a result an arm
can be built on, and it is exactly how a mis-set wing looks from the outside.

  python tools/score_wing.py --wing chameleon_bench --system s18-advisor-ladder
  python tools/score_wing.py --system s19-tejas-noadv --compare s20-tejas-adv
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

import yaml

from chi_edge_bench import paths
from chi_edge_bench.harness.checks import extract_ranked_types
from chi_edge_bench.harness.runner import evaluate

#: Item id prefix per wing. The chameleon wing splits its 72 items into CB
#: (core) and RB (reservation); the edge wing's are R-prefixed.
SUITES = {
    "chameleon_bench": {"reservation": "RB", "core": "CB", "all": ""},
    "chi_edge_bench": {"reservation": "R", "all": ""},
}


def load_items(wing: str, suite: str):
    prefix = SUITES.get(wing, {}).get(suite)
    if prefix is None:
        raise SystemExit(f"unknown suite {suite!r} for wing {wing!r}; "
                         f"try {sorted(SUITES.get(wing, {}))}")
    return sorted(paths.items_dir().glob(f"{prefix}*.yaml"))


def score(arm: str, condition: str, items):
    """Run every item's own checkers against that arm's answer."""
    runs = paths.runs_dir() / condition / arm
    groups = collections.defaultdict(lambda: [0, 0])
    checks = collections.defaultdict(lambda: [0, 0])
    rows, missing = [], []

    for path in items:
        item = yaml.safe_load(path.read_text(encoding="utf-8"))
        answer = runs / f"{item['id']}.md"
        if not answer.is_file():
            missing.append(item["id"])
            continue
        text = answer.read_text(encoding="utf-8")
        report_ = evaluate(item, text)
        for r in report_["results"]:
            for tally in (groups[r["group"]], checks[r["check"]]):
                tally[0] += bool(r["passed"])
                tally[1] += 1
        rows.append({
            "item": item["id"],
            "named_real_types": bool(extract_ranked_types(text)),
            "feasible": item.get("feasible"),
            "all_passed": report_["all_passed"],
            "failed": ";".join(r["check"] for r in report_["results"]
                               if not r["passed"]),
        })
    return {"arm": arm, "rows": rows, "missing": missing,
            "groups": dict(groups), "checks": dict(checks)}


def vacuity_warning(result) -> str:
    """Flag an arm whose passes are the checkers finding nothing to grade.

    Several checkers are satisfied by silence. `no_down_types_listed` passes
    when no recommended type is fully reserved - and an answer naming no real
    node type at all recommends nothing, so it passes. `forbidden_calls`
    passes when the answer contains no forbidden call, which an answer
    containing no code does.

    An arm can therefore post 100% on safety while being unable to name a
    single piece of hardware that exists. That is not a strength and must not
    be read as one, so it is said out loud next to the number rather than left
    for somebody to discover.

    Counted over the SATISFIABLE items only. On an infeasible item naming
    nothing is the correct answer, and an earlier version of this note counted
    those too: it reported the advisor arm as 11 of 32 vacuous when all eleven
    were correct abstentions. A warning that fires on the right answer teaches
    people to skip the warning.
    """
    rows = [r for r in result["rows"] if r["feasible"] is not False]
    if not rows:
        return ""
    named = sum(1 for r in rows if r["named_real_types"])
    if named == len(rows):
        return ""
    return (f"  NOTE: {len(rows) - named} of {len(rows)} answers to SATISFIABLE "
            f"items name no node type the capability table knows. Checks that "
            f"pass by finding nothing to object to - no_down_types_listed, "
            f"forbidden_calls - are passing vacuously for those items. "
            f"names_known_type grades this; the safety group still does not.")


def _pct(t):
    return f"{100 * t[0] / t[1]:5.1f}%" if t[1] else "    -"


def report(result, verbose=True):
    rows, n = result["rows"], len(result["rows"])
    passed = sum(1 for r in rows if r["all_passed"])
    print(f"\narm={result['arm']}  scored={n}  missing={len(result['missing'])}")
    if n:
        print(f"  all checks pass : {passed}/{n} ({100 * passed / n:.1f}%)")
    named = sum(1 for r in rows if r["named_real_types"])
    print(f"  names real hardware : {named}/{n}")
    print("\n  by group:")
    for g, t in sorted(result["groups"].items()):
        print(f"    {g:14} {t[0]:3}/{t[1]:<3} {_pct(t)}")
    warning = vacuity_warning(result)
    if warning:
        print()
        print(warning)
    if verbose:
        print("\n  by check:")
        for c, t in sorted(result["checks"].items(),
                           key=lambda kv: kv[1][0] / kv[1][1] if kv[1][1] else 0):
            print(f"    {c:26} {t[0]:3}/{t[1]:<3} {_pct(t)}")
        bad = [r for r in rows if not r["all_passed"]]
        if bad:
            print("\n  items with failures:")
            for r in bad:
                print(f"    {r['item']}  feasible={str(r['feasible']):5} "
                      f"failed: {r['failed']}")
    if result["missing"]:
        print(f"\n  no answer file: {', '.join(result['missing'][:12])}"
              + (" ..." if len(result["missing"]) > 12 else ""))


def compare(a, b):
    """Two arms side by side, and the items where they disagree.

    The per-item disagreement is the point. Two arms landing on the same total
    by passing different items is a different finding from two arms agreeing,
    and a summary row cannot tell them apart.
    """
    print(f"\n{'':26} {a['arm']:>22} {b['arm']:>22}")
    print("-" * 74)
    for g in sorted(set(a["groups"]) | set(b["groups"])):
        ta, tb = a["groups"].get(g, [0, 0]), b["groups"].get(g, [0, 0])
        print(f"  {g:24} {_pct(ta):>22} {_pct(tb):>22}")
    pa = {r["item"]: r["all_passed"] for r in a["rows"]}
    pb = {r["item"]: r["all_passed"] for r in b["rows"]}
    print(f"  {'all checks pass':24} "
          f"{f'{sum(pa.values())}/{len(pa)}':>22} "
          f"{f'{sum(pb.values())}/{len(pb)}':>22}")
    only_a = sorted(i for i in pa if pa[i] and not pb.get(i, False))
    only_b = sorted(i for i in pb if pb[i] and not pa.get(i, False))
    print(f"\n  passes only in {a['arm']}: {', '.join(only_a) or 'none'}")
    print(f"  passes only in {b['arm']}: {', '.join(only_b) or 'none'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wing", default="chameleon_bench", choices=sorted(SUITES))
    ap.add_argument("--suite", default="reservation")
    ap.add_argument("--condition", default="baremetal_reservation")
    ap.add_argument("--system", required=True, help="arm to score")
    ap.add_argument("--compare", default="", help="second arm, scored alongside")
    ap.add_argument("--csv", default="", help="write per-item rows here")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    # P2: the wing is process state, and a run that forgets it grades one
    # wing's answers against the other's hardware. Set explicitly, always.
    paths.set_wing(args.wing)

    items = load_items(args.wing, args.suite)
    if not items:
        print(f"ERROR: no {args.suite} items under {paths.items_dir()}",
              file=sys.stderr)
        return 2

    first = score(args.system, args.condition, items)
    if not first["rows"]:
        print(f"ERROR: no answers for {args.system} under "
              f"{paths.runs_dir() / args.condition}; nothing was scored",
              file=sys.stderr)
        return 2
    report(first, verbose=not args.quiet)

    second = None
    if args.compare:
        second = score(args.compare, args.condition, items)
        if not second["rows"]:
            print(f"ERROR: no answers for {args.compare}", file=sys.stderr)
            return 2
        report(second, verbose=not args.quiet)
        compare(first, second)

    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, ["arm", "item", "feasible",
                                    "named_real_types", "all_passed", "failed"])
            w.writeheader()
            for res in (first, second):
                if res:
                    for row in res["rows"]:
                        w.writerow({"arm": res["arm"], **row})
        print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
