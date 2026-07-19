"""
Gold admission gate (decision D06): every item's gold_spec must pass 100% of its
own checkers (and, for V1 items, its snapshot execution) before the item is part
of the benchmark. A failing gold is a defective item, never a defective gold.

  python -m harness.validate_golds            # gate all items
  python -m harness.validate_golds P16 N04    # gate a subset

Writes exports/gate_report.json. Exit code 0 iff all golds pass.
"""

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "snapshots" / "snapshot_synthetic_2026-07-04.json"


def main():
    only = set(sys.argv[1:])
    reports, failed = [], []
    for p in sorted((ROOT / "items").glob("*.yaml")):
        item = yaml.safe_load(p.read_text())
        if only and item["id"] not in only:
            continue
        text = "```python\n" + item["gold_spec"] + "\n```"
        rep = evaluate(item, text, SNAPSHOT)
        reports.append(rep)
        status = "PASS" if rep["all_passed"] else "FAIL"
        print(f"{item['id']:<6} {status}")
        if not rep["all_passed"]:
            failed.append(item["id"])
            for r in rep["results"]:
                if not r["passed"]:
                    print(f"        x {r['check']}[{r['group']}]: {r['detail']}")
    (ROOT / "exports").mkdir(exist_ok=True)
    (ROOT / "exports" / "gate_report.json").write_text(json.dumps(reports, indent=2))
    n = len(reports)
    print(f"\nGate: {n - len(failed)}/{n} golds pass their own checkers.")
    if failed:
        print("REJECTED (fix gold or checkers, log in benchmark_v4_decisions.md):",
              ", ".join(failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
