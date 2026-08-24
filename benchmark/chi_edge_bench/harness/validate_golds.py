"""
Gold admission gate (decision D06): every item's gold_spec must pass 100% of its
own checkers (and, for V1 items, its snapshot execution) before the item is part
of the benchmark. A failing gold is a defective item, never a defective gold.

  chi-edge-bench selftest                    # gate every item
  chi-edge-bench selftest --suite core       # the frozen 50 only
  chi-edge-bench selftest P16 N04            # gate a subset

Writes exports/gate_report.json for the core suite, gate_report_<suite>.json
otherwise, so a v5 run cannot overwrite the cited core artifact. Exit code 0 iff
all golds pass.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from chi_edge_bench.harness.runner import evaluate
from chi_edge_bench.paths import default_snapshot, exports_dir, items_dir


def as_answer(item: dict) -> str:
    """Render a gold the way a model would submit it.

    Only code answers get fenced. A reservation gold is a ranked prose list, and
    wrapping it in ```python would make extract_code hand the checkers a blob
    that cannot parse.
    """
    gold = item["gold_spec"]
    if item.get("expected_answer_type", "code") == "code":
        return "```python\n" + gold + "\n```"
    return gold


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*", help="gate only these item ids")
    ap.add_argument("--suite", default="all",
                    choices=["all", "core", "reservation"],
                    help="core = the frozen 50; reservation = the v5 R items")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    only = set(args.ids)
    reports, failed = [], []
    for p in sorted(items_dir().glob("*.yaml")):
        item = yaml.safe_load(p.read_text())
        if only and item["id"] not in only:
            continue
        # Items predating v5 carry no `suite` key; they are the core suite.
        if args.suite != "all" and item.get("suite", "core") != args.suite:
            continue
        rep = evaluate(item, as_answer(item), default_snapshot())
        reports.append(rep)
        status = "PASS" if rep["all_passed"] else "FAIL"
        print(f"{item['id']:<6} {status}")
        if not rep["all_passed"]:
            failed.append(item["id"])
            for r in rep["results"]:
                if not r["passed"]:
                    print(f"        x {r['check']}[{r['group']}]: {r['detail']}")
    exports_dir().mkdir(parents=True, exist_ok=True)
    # gate_report.json is the cited core artifact; only a core run may claim it.
    default = ("gate_report.json" if args.suite == "core"
               else f"gate_report_{args.suite}.json")
    out = args.out or (exports_dir() / default)
    out.write_text(json.dumps(reports, indent=2))
    n = len(reports)
    print(f"\nGate: {n - len(failed)}/{n} golds pass their own checkers.")
    if failed:
        print("REJECTED (fix gold or checkers, log in benchmark_v4_decisions.md):",
              ", ".join(failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
