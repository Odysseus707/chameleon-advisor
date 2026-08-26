"""score_runs: batch-score runs/ and build the comparison tables.

Read-only over harness/ and items/ (imports the scorer, changes nothing).
Scores every runs/<condition>/<system>/<ITEM>.md exactly like the notebook
batch cell (harness.runner.evaluate on the verbatim text), then aggregates:

  1. fill status per (condition, system)
  2. overall PASS rates per system x condition
  3. per-group (mechanism/specifics/safety) pass rates  — the H0/H1 table
  4. advisor ablation on blind: s4-fork-on vs s5-fork-off, incl. item flips
  5. uncovered items: abstain_or_discover outcomes per system
  6. fence lint: filled answers whose code the extractor cannot see

--wrap-code applies calibrate_v3.wrap_code_blocks IN MEMORY before scoring
(answers on disk are never touched: runs/ is the measurement record). A row
scored from recovered text has recovered=True in the CSV.

Usage:
  chi-edge-bench score-runs                 # score + summary
  chi-edge-bench score-runs --wrap-code     # with fence recovery
  chi-edge-bench score-runs --conditions blind --systems s10-... ,s11-...
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

from chi_edge_bench.harness.checks import extract_ranked_types
from chi_edge_bench.harness.runner import evaluate, extract_code, load_item
from chi_edge_bench.paths import (default_snapshot, exports_dir, items_dir,
                                  runs_dir, workspace, workspace_source)

try:  # calibrate_v3 imports openpyxl at module level; recovery is optional
    from chi_edge_bench.tools.calibrate_v3 import wrap_code_blocks
except ImportError:  # pragma: no cover
    wrap_code_blocks = None
# Reservation items name their own snapshot, which runner.resolve_snapshot
# honours over this default.
CORE_GROUPS = ("mechanism", "specifics", "safety")
RESERVATION_GROUPS = ("feasibility", "capability")
GROUPS = CORE_GROUPS + RESERVATION_GROUPS


def active_groups(rows):
    """Only groups that actually ran. Keeps a core-only report identical to v4
    instead of padding it with two empty reservation rows - and stops a blended
    headline rate from ever appearing, since the two families never co-occur in
    one item."""
    return [g for g in GROUPS
            if any((r.get(f"{g}_total") or 0) for r in rows)]
CONDITION_ORDER = ("blind", "matched", "heldout", "uncovered")
# Four systems, contiguous. Earlier numbering ran to s9 because dropped arms
# left gaps that new arms were appended past; the freed slots are reused instead.
#   s1  historical baseline - the source of the numbers in the deck
#   s2  reference ceiling, different hardware: NOT a controlled comparison
#   s3/s4  the controlled pair - same docs RAG, model and P100, advisor off/on
# Superseded arms (fork-on/fork-off) and the advisor component test live in
# runs_archive/, outside runs/ so they are not scored as a bogus condition.
SYSTEM_ORDER = ("s1-chatbot", "s2-sonnet", "s3-chatbot-noadv", "s4-chatbot-adv")


def sort_key(name, order):
    return (order.index(name), name) if name in order else (len(order), name)


def score_all(conditions, systems, wrap_code, suite=""):
    rows, items_cache = [], {}
    for path in sorted(runs_dir().glob("*/*/*.md")):
        parts = path.relative_to(runs_dir()).parts
        if len(parts) != 3:
            print(f"  WARN: {path} is not runs/<cond>/<system>/<ITEM>.md — skipped",
                  file=sys.stderr)
            continue
        cond, system, fname = parts
        stem = fname[:-3]
        if conditions and cond not in conditions:
            continue
        if systems and system not in systems:
            continue
        item_path = items_dir() / f"{stem}.yaml"
        if not item_path.exists():
            print(f"  WARN: {path} has no items/{stem}.yaml — skipped", file=sys.stderr)
            continue
        if stem not in items_cache:
            items_cache[stem] = load_item(item_path)
        # Items predating v5 carry no `suite` key; they are the core suite.
        if suite and items_cache[stem].get("suite", "core") != suite:
            continue
        text = path.read_text(encoding="utf-8")
        row = {"condition": cond, "system": system, "item": stem,
               "status": "scored", "fences": "```" in text,
               "recovered": False, "code_seen": False, "all_passed": "",
               "failed_checks": "", "rank1": ""}
        # Every group gets a column so the CSV schema is stable across suites;
        # the markdown report then renders only the groups that actually ran.
        for g in GROUPS:
            row[f"{g}_passed"], row[f"{g}_total"] = "", ""
        if not text.strip():
            row["status"] = "empty"
            rows.append(row)
            continue
        scored_text = text
        if wrap_code and wrap_code_blocks is not None and "```" not in text:
            wrapped, n = wrap_code_blocks(text)
            if n > 0:
                scored_text, row["recovered"] = wrapped, True
        row["code_seen"] = bool(extract_code(scored_text).strip())
        if items_cache[stem].get("expected_answer_type") == "ranked_list":
            # The top pick is what a user would act on, and comparing it across
            # environments is what makes state-sensitivity measurable.
            picks = extract_ranked_types(scored_text)
            row["rank1"] = picks[0] if picks else ""
        rep = evaluate(items_cache[stem], scored_text, default_snapshot())
        row["all_passed"] = rep["all_passed"]
        row["failed_checks"] = " ".join(r["check"] for r in rep["results"]
                                        if not r["passed"])
        for g, v in rep["groups"].items():
            row[f"{g}_passed"], row[f"{g}_total"] = v["passed"], v["total"]
        rows.append(row)
    return rows


# ---------------------------------------------------------------- aggregation

def cell_key(r):
    return (r["condition"], r["system"])


def table(header, lines):
    out = [header, "-" * len(header)]
    out += lines
    return "\n".join(out) + "\n"


def fmt_rate(p, t):
    return f"{p}/{t} ({p / t:.0%})" if t else "—"


def _colw(systems):
    """Column width that actually fits the system names.

    Was a hardcoded 14, which silently ran headers together once arm names grew
    past it - "s10-llama70b-tejas-noadvs12-claude-artifacts" in one cell.
    """
    return max(14, max((len(s) for s in systems), default=0) + 2)


def summarize(rows, items_cache=None):
    scored = [r for r in rows if r["status"] == "scored"]
    active = active_groups(scored)
    conds = sorted({r["condition"] for r in rows}, key=lambda c: sort_key(c, CONDITION_ORDER))
    systems = sorted({r["system"] for r in rows}, key=lambda s: sort_key(s, SYSTEM_ORDER))
    out = ["# Run scores summary", ""]

    # 1. fill status
    out.append("## Fill status (non-empty / total answer files)\n")
    by_cell = defaultdict(list)
    for r in rows:
        by_cell[cell_key(r)].append(r)
    hdr = f"{'condition':10}" + "".join(f"{s:>{_colw(systems)}}" for s in systems)
    lines = []
    for c in conds:
        cells = []
        for s in systems:
            rs = by_cell.get((c, s), [])
            cells.append(f"{sum(x['status'] == 'scored' for x in rs)}/{len(rs)}"
                         if rs else "—")
        lines.append(f"{c:10}" + "".join(f"{x:>{_colw(systems)}}" for x in cells))
    out.append(table(hdr, lines))

    # 2. overall pass rates
    out.append("## Overall PASS rate (all checkers green; scored answers only)\n")
    lines = []
    for c in conds:
        cells = []
        for s in systems:
            rs = [x for x in by_cell.get((c, s), []) if x["status"] == "scored"]
            cells.append(fmt_rate(sum(bool(x["all_passed"]) for x in rs), len(rs))
                         if rs else "—")
        lines.append(f"{c:10}" + "".join(f"{x:>{_colw(systems)}}" for x in cells))
    out.append(table(hdr, lines))

    # 2b. common-item subset — selection-bias guard for unequal fills:
    # partial fills mean each system may have answered a *different* (possibly
    # easier) subset, so raw rates are not comparable; this table recomputes
    # everything on the intersection of items every data-bearing system answered.
    out.append("## Rates on COMMON items only (selection-bias guard)\n")
    any_common = False
    for c in conds:
        sys_with = [s for s in systems
                    if any(x["status"] == "scored" for x in by_cell.get((c, s), []))]
        if len(sys_with) < 2:
            continue
        item_sets = [{x["item"] for x in by_cell[(c, s)] if x["status"] == "scored"}
                     for s in sys_with]
        common = set.intersection(*item_sets)
        if not common:
            out.append(f"  {c}: systems with data share no common items yet\n")
            continue
        any_common = True
        out.append(f"### {c} — {len(common)} items answered by all of: "
                   f"{', '.join(sys_with)}\n")
        hdr3 = f"{'metric':10}" + "".join(f"{s:>{_colw(sys_with)}}" for s in sys_with)
        lines = []
        cells = []
        for s in sys_with:
            rs = [x for x in by_cell[(c, s)]
                  if x["item"] in common and x["status"] == "scored"]
            cells.append(fmt_rate(sum(bool(x["all_passed"]) for x in rs), len(rs)))
        lines.append(f"{'PASS':10}" + "".join(f"{x:>{_colw(systems)}}" for x in cells))
        for g in active:
            cells = []
            for s in sys_with:
                rs = [x for x in by_cell[(c, s)]
                      if x["item"] in common and x["status"] == "scored"]
                p = sum(x[f"{g}_passed"] or 0 for x in rs)
                t = sum(x[f"{g}_total"] or 0 for x in rs)
                cells.append(fmt_rate(p, t))
            lines.append(f"{g:10}" + "".join(f"{x:>{_colw(systems)}}" for x in cells))
        out.append(table(hdr3, lines))
    if not any_common:
        out.append("  (fewer than two systems share scored items anywhere)\n")

    # 3. per-group rates — the H0/H1 instrument
    out.append("## Checker-group pass rates (checks passed / checks run)\n")
    for g in active:
        out.append(f"### {g}\n")
        lines = []
        for c in conds:
            cells = []
            for s in systems:
                rs = [x for x in by_cell.get((c, s), []) if x["status"] == "scored"]
                p = sum(x[f"{g}_passed"] or 0 for x in rs)
                t = sum(x[f"{g}_total"] or 0 for x in rs)
                cells.append(fmt_rate(p, t) if rs else "—")
            lines.append(f"{c:10}" + "".join(f"{x:>{_colw(systems)}}" for x in cells))
        out.append(table(hdr, lines))

    # 3b. state-sensitivity — the reservation suite's headline metric
    # Over environment pairs where the GOLD top pick changes, how often does the
    # system's top pick change too? A system that recites one favourite device
    # regardless of live state scores near zero here, however good its prose.
    # Only synthetic counterfactuals make this measurable: the recorded capture
    # is a single environment and cannot separate reading state from guessing.
    res = [r for r in scored if r.get("rank1") is not None and r.get("rank1") != ""]
    if res:
        import yaml as _yaml
        meta = {}
        for stem in {r["item"] for r in res}:
            it = _yaml.safe_load((items_dir() / f"{stem}.yaml").read_text())
            gold = extract_ranked_types(it["gold_spec"])
            meta[stem] = (it.get("stem"), gold[0] if gold else "")
        out.append("## State-sensitivity (does the pick track the environment?)\n")
        lines = []
        for s in systems:
            by_stem = defaultdict(list)
            for r in res:
                if r["system"] != s:
                    continue
                key, gold1 = meta[r["item"]]
                by_stem[(r["condition"], key)].append((gold1, r["rank1"]))
            moved = tracked = 0
            for pairs in by_stem.values():
                for i in range(len(pairs)):
                    for j in range(i + 1, len(pairs)):
                        if pairs[i][0] != pairs[j][0]:      # gold moved
                            moved += 1
                            tracked += pairs[i][1] != pairs[j][1]
            if moved:
                lines.append(f"{s:14} {fmt_rate(tracked, moved):>16}")
        out.append(table(f"{'system':14}{'tracked/moved':>16}", lines)
                   if lines else "  (no environment pairs with differing golds yet)\n")

    # 4. advisor ablation (blind, s4 vs s5)
    s4 = {r["item"]: r for r in scored
          if r["system"] == "s4-fork-on" and r["condition"] == "blind"}
    s5 = {r["item"]: r for r in scored
          if r["system"] == "s5-fork-off" and r["condition"] == "blind"}
    common = sorted(set(s4) & set(s5))
    if common:
        out.append("## Advisor ablation (blind): s4-fork-on vs s5-fork-off\n")
        w4 = sum(bool(s4[i]["all_passed"]) for i in common)
        w5 = sum(bool(s5[i]["all_passed"]) for i in common)
        out.append(f"items compared: {len(common)} | s4 PASS {w4} | s5 PASS {w5} "
                   f"| delta {w4 - w5:+d}\n")
        for g in active:
            p4 = sum(s4[i][f"{g}_passed"] or 0 for i in common)
            t4 = sum(s4[i][f"{g}_total"] or 0 for i in common)
            p5 = sum(s5[i][f"{g}_passed"] or 0 for i in common)
            t5 = sum(s5[i][f"{g}_total"] or 0 for i in common)
            out.append(f"  {g:10} s4 {fmt_rate(p4, t4):>14}   s5 {fmt_rate(p5, t5):>14}")
        flips_up = [i for i in common if s4[i]["all_passed"] and not s5[i]["all_passed"]]
        flips_dn = [i for i in common if s5[i]["all_passed"] and not s4[i]["all_passed"]]
        out.append(f"\n  advisor fixes (s4 PASS, s5 FAIL): {', '.join(flips_up) or 'none'}")
        out.append(f"  advisor breaks (s5 PASS, s4 FAIL): {', '.join(flips_dn) or 'none'}\n")

    # 5. uncovered outcomes
    unc = [r for r in scored if r["condition"] == "uncovered"]
    if unc:
        out.append("## Uncovered items (abstain-or-discover)\n")
        for r in sorted(unc, key=lambda x: (x["item"], sort_key(x["system"], SYSTEM_ORDER))):
            verdict = "PASS" if r["all_passed"] else f"FAIL [{r['failed_checks']}]"
            out.append(f"  {r['item']:5} {r['system']:14} {verdict}")
        out.append("")

    # 6. fence lint
    blind_spots = [r for r in scored if not r["code_seen"]]
    out.append("## Fence lint (scored answers where the extractor sees NO code)\n")
    if not blind_spots:
        out.append("  none — every scored answer yielded parseable code\n")
    else:
        out.append("  These score near-zero mechanically. If the answer visibly contains")
        out.append("  code, the fences were stripped on paste — re-paste or --wrap-code.")
        out.append("  (Prose-only answers to abstention items are fine here.)\n")
        for r in blind_spots:
            note = "recovered" if r["recovered"] else \
                ("no fences" if not r["fences"] else "fenced but unparseable")
            out.append(f"  {r['condition']}/{r['system']}/{r['item']}.md  [{note}]")
        out.append("")

    # 7. per-item verdict matrix
    out.append("## Item x system verdicts (P pass, f fail, . empty, blank no file)\n")
    for c in conds:
        by_item = defaultdict(dict)
        for r in rows:
            if r["condition"] == c:
                by_item[r["item"]][r["system"]] = r
        if not by_item:
            continue
        out.append(f"### {c}\n")
        hdr2 = f"{'item':6}" + "".join(f"{s.split('-')[0]:>5}" for s in systems)
        lines = []
        for item in sorted(by_item):
            marks = []
            for s in systems:
                r = by_item[item].get(s)
                if r is None:
                    marks.append("")
                elif r["status"] == "empty":
                    marks.append(".")
                else:
                    marks.append("P" if r["all_passed"] else "f")
            lines.append(f"{item:6}" + "".join(f"{m:>5}" for m in marks))
        out.append(table(hdr2, lines))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wrap-code", action="store_true",
                    help="in-memory fence recovery (calibrate_v3.wrap_code_blocks) "
                         "for answers with no ``` fences; files are never modified")
    ap.add_argument("--conditions", default="",
                    help="comma-separated filter (default: all)")
    ap.add_argument("--systems", default="", help="comma-separated filter (default: all)")
    ap.add_argument("--suite", default="", choices=["", "core", "reservation"],
                    help="core = the frozen 50; reservation = the v5 R items")
    ap.add_argument("--csv", default=str(exports_dir() / "run_scores.csv"))
    ap.add_argument("--md", default=str(exports_dir() / "run_summary.md"))
    ap.add_argument("--todo", action="store_true",
                    help="just list the empty answer files (paste worklist) and exit")
    args = ap.parse_args()

    if args.todo:
        empties = [p for p in sorted(runs_dir().glob("*/*/*.md"))
                   if len(p.relative_to(runs_dir()).parts) == 3
                   and not p.read_text(encoding="utf-8").strip()]
        for p in empties:
            print(p.relative_to(workspace()))
        print(f"[{len(empties)} empty answer files]")
        return

    if args.wrap_code and wrap_code_blocks is None:
        raise SystemExit("--wrap-code needs calibrate_v3 (openpyxl missing?)")
    conditions = {c.strip() for c in args.conditions.split(",") if c.strip()}
    systems = {s.strip() for s in args.systems.split(",") if s.strip()}

    rows = score_all(conditions, systems, args.wrap_code, args.suite)
    if not rows:
        raise SystemExit(
            f"no answer files matched under {runs_dir()}\n"
            f"(workspace chosen by: {workspace_source()})")

    fields = list(rows[0].keys())
    # A fresh workspace has no exports/ yet; the repo one already does.
    Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
    Path(args.md).parent.mkdir(parents=True, exist_ok=True)
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    summary = summarize(rows)
    Path(args.md).write_text(summary + "\n", encoding="utf-8")
    print(summary)
    print(f"[written] {args.csv}")
    print(f"[written] {args.md}")


if __name__ == "__main__":
    main()
