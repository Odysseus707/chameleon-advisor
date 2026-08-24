#!/usr/bin/env python3
"""Compile the whole benchmark - both suites - into one workbook.

Every question, every gold answer, every tag and every checker for all items, in
one file you can hand to someone or put on a slide. Core (the frozen 50) and
reservation (the 84 v5 items) sit in the same sheet with a `suite` column, because
they are one benchmark, not two.

Sheets:
  All items      one row per item, questions + golds + tags, both suites
  Checkers       one row per checker, so the grading surface is inspectable
  Tags           trap_tags / category / axis / checker frequencies
  Results        latest scored run per item, if exports/*scores*.csv exist
  Summary        counts that should match the gate output

  python tools/compile_benchmark.py
  python tools/compile_benchmark.py --out exports/benchmark_complete.xlsx

Golds are included in full. This file is therefore the ANSWER KEY - do not paste
it into a model you are about to benchmark.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "exports" / "benchmark_complete.xlsx"

HDR_FILL = PatternFill("solid", fgColor="1F4E79")
HDR_FONT = Font(bold=True, color="FFFFFF")
SUITE_FILL = {"core": "DDEBF7", "reservation": "E2EFDA"}


def flat(v) -> str:
    if isinstance(v, dict):
        return "; ".join(f"{k}={flat(x)}" for k, x in v.items() if x not in (None, [], {}))
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return "" if v is None else str(v)


def load_items() -> list:
    out = []
    for p in sorted((ROOT / "items").glob("*.yaml")):
        it = yaml.safe_load(p.read_text())
        it["_suite"] = it.get("suite", "core")
        out.append(it)
    # Core first, then reservation; id order within each.
    return sorted(out, key=lambda i: (i["_suite"] != "core", i["id"]))


def load_results() -> dict:
    """Per-item outcomes from any exports/*scores*.csv."""
    res = {}
    for csvp in sorted((ROOT / "exports").glob("*scores*.csv")):
        try:
            for r in csv.DictReader(csvp.open()):
                if r.get("status") != "scored":
                    continue
                res.setdefault(r["item"], []).append(
                    (r.get("system", "?"), r.get("all_passed"),
                     r.get("failed_checks", ""), csvp.name))
        except (OSError, csv.Error):
            continue
    return res


def sheet(wb, title, cols, rows, widths=None, wrap=()):
    ws = wb.active if wb.sheetnames == ["Sheet"] else wb.create_sheet(title)
    ws.title = title
    ws.append(cols)
    for c in range(1, len(cols) + 1):
        ws.cell(row=1, column=c).font = HDR_FONT
        ws.cell(row=1, column=c).fill = HDR_FILL
    for r in rows:
        ws.append([r.get(c, "") for c in cols])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, c in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = \
            (widths or {}).get(c, min(max(11, len(c) + 2), 42))
        if c in wrap:
            for cell in ws[get_column_letter(i)][1:]:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    return ws


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    items, results = load_items(), load_results()
    wb = Workbook()

    # -- All items ---------------------------------------------------------
    cols = ["id", "suite", "version", "category", "axis", "coverage", "snapshot",
            "stem", "environment", "prompt", "gold_answer", "answer_type",
            "verification", "designed_trap", "trap_tags", "target_artifact",
            "fed_blind", "fed_matched", "fed_heldout", "key_tokens",
            "requires", "count", "hours", "feasible", "n_checkers",
            "checker_groups", "api_anchor", "lineage", "gold_provenance"]
    rows = []
    for it in items:
        fed = it.get("fed_sets") or {}
        chk = it.get("checkers") or []
        rows.append({
            "id": it["id"], "suite": it["_suite"], "version": it.get("version"),
            "category": it.get("category"), "axis": it.get("axis"),
            "coverage": it.get("coverage", ""), "snapshot": it.get("snapshot", ""),
            "stem": it.get("stem", ""), "environment": it.get("environment_note", ""),
            "prompt": it.get("prompt"), "gold_answer": it.get("gold_spec"),
            "answer_type": it.get("expected_answer_type", "code"),
            "verification": it.get("verification_level"),
            "designed_trap": it.get("designed_trap"),
            "trap_tags": flat(it.get("trap_tags")),
            "target_artifact": flat(it.get("target_artifact")),
            "fed_blind": flat(fed.get("blind")),
            "fed_matched": flat(fed.get("matched")),
            "fed_heldout": flat(fed.get("heldout")),
            "key_tokens": flat(it.get("key_tokens")),
            "requires": flat(it.get("requires")),
            "count": it.get("requested_count", ""),
            "hours": it.get("requested_hours", ""),
            "feasible": it.get("feasible", ""),
            "n_checkers": len(chk),
            "checker_groups": flat(sorted({c.get("group", "mechanism") for c in chk})),
            "api_anchor": it.get("api_anchor", ""),
            "lineage": it.get("lineage", ""),
            "gold_provenance": it.get("gold_provenance", ""),
        })
    ws = sheet(wb, "All items", cols, rows,
               {"prompt": 60, "gold_answer": 80, "designed_trap": 46,
                "gold_provenance": 50, "category": 28},
               wrap=("prompt", "gold_answer", "designed_trap", "gold_provenance"))
    for i, r in enumerate(rows, start=2):
        ws.cell(row=i, column=2).fill = PatternFill(
            "solid", fgColor=SUITE_FILL.get(r["suite"], "F2F2F2"))

    # -- Checkers ----------------------------------------------------------
    crows = []
    for it in items:
        for c in it.get("checkers") or []:
            params = {k: v for k, v in c.items() if k not in ("check", "group")}
            crows.append({"item": it["id"], "suite": it["_suite"],
                          "check": c.get("check"),
                          "group": c.get("group", "mechanism"),
                          "params": flat(params)})
    sheet(wb, "Checkers", ["item", "suite", "check", "group", "params"], crows,
          {"params": 70}, wrap=("params",))

    # -- Tags --------------------------------------------------------------
    trows = []
    for field, label in (("trap_tags", "trap_tag"), ("category", "category"),
                         ("axis", "axis"), ("coverage", "coverage")):
        counts = Counter()
        for it in items:
            v = it.get(field)
            for x in (v if isinstance(v, list) else [v]):
                if x:
                    counts[str(x)] += 1
        for k, n in counts.most_common():
            trows.append({"dimension": label, "value": k, "items": n})
    check_counts = Counter(c["check"] for c in crows)
    for k, n in check_counts.most_common():
        trows.append({"dimension": "checker", "value": k, "items": n})
    group_counts = Counter(c["group"] for c in crows)
    for k, n in group_counts.most_common():
        trows.append({"dimension": "checker_group", "value": k, "items": n})
    sheet(wb, "Tags", ["dimension", "value", "items"], trows, {"value": 34})

    # -- Results -----------------------------------------------------------
    rrows = []
    for it in items:
        for system, passed, failed, src in results.get(it["id"], []):
            rrows.append({"item": it["id"], "suite": it["_suite"],
                          "system": system, "all_passed": passed,
                          "failed_checks": failed, "source": src})
    sheet(wb, "Results", ["item", "suite", "system", "all_passed",
                          "failed_checks", "source"], rrows,
          {"failed_checks": 60}, wrap=("failed_checks",))

    # -- Summary -----------------------------------------------------------
    by_suite = Counter(i["_suite"] for i in items)
    srows = [{"metric": "items total", "value": len(items)}]
    srows += [{"metric": f"items, suite={s}", "value": n}
              for s, n in sorted(by_suite.items())]
    srows += [
        {"metric": "checkers total", "value": len(crows)},
        {"metric": "distinct checker types", "value": len(check_counts)},
        {"metric": "items with a gold answer",
         "value": sum(1 for i in items if i.get("gold_spec"))},
        {"metric": "reservation: covered",
         "value": sum(1 for i in items if i.get("coverage") == "covered")},
        {"metric": "reservation: uncovered",
         "value": sum(1 for i in items if i.get("coverage") == "uncovered")},
        {"metric": "reservation: abstention controls",
         "value": sum(1 for i in items if i.get("feasible") is False)},
        {"metric": "scored rows found", "value": len(rrows)},
    ]
    sheet(wb, "Summary", ["metric", "value"], srows, {"metric": 34})

    args.out.parent.mkdir(exist_ok=True)
    wb.save(args.out)
    print(f"[written] {args.out}")
    for r in srows:
        print(f"  {r['metric']:<34} {r['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
