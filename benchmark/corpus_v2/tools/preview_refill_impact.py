#!/usr/bin/env python3
"""preview_refill_impact: what refilling the capability table would do to the golds.

  python corpus_v2/tools/preview_refill_impact.py

Writes exports/refill_impact_<date>.md and WRITES NOTHING ELSE. No table, no
item, no snapshot. The point is to see the whole consequence before any of it
is committed to, because the consequence is larger than it looks: ram_gb and
vcpus are not only filter inputs, they are two of the four terms in
`ranking.capability_score`, which is the tiebreaker in EVERY ranking. So a
refill reaches items that never mention memory.

THE SELF-CHECK THAT MAKES THE DIFF MEAN ANYTHING
Before comparing anything, every item is rebuilt from the CURRENT table and
compared to what is on disk. If those disagree the item bank is not reproducible
from its inputs, and a diff against a rebuild would be measuring drift that was
already there rather than the change under review. That check is fatal on
purpose.

WHAT IT DELIBERATELY DOES NOT DO
It does not re-solve against live Blazar. The golds are solved against pinned
snapshots (D40) and a live re-solve measures what time it is (R7). Only the
capability table moves here; every free count is the one already recorded.
"""
from __future__ import annotations

import copy
import difflib
import re
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
sys.path.insert(0, str(HERE))

import build_reservation_items as B          # noqa: E402
import refill_capability_table as R          # noqa: E402

ITEMS = BENCH / "chameleon_bench" / "data" / "items"
EXPORTS = BENCH / "exports"


def proposed_table(base: dict) -> tuple[dict, list[str]]:
    """The table as it would be after the refill, in memory only."""
    cap = json.loads(R.latest_capture().read_text())
    ref = cap["node_types"]
    by_cpu = R.threads_by_cpu(ref)
    out = copy.deepcopy(base)
    notes = []
    for name, spec in out["node_types"].items():
        e = ref.get(name)
        if not e:
            notes.append(f"{name}: kept Blazar values (absent from reference API)")
            continue
        d = R.derive(e, by_cpu)
        if spec.get("ram_gb") != d["ram_gb"] or spec.get("vcpus") != d["vcpus"]:
            notes.append(f"{name}: ram_gb {spec.get('ram_gb')} -> {d['ram_gb']}, "
                         f"vcpus {spec.get('vcpus')} -> {d['vcpus']}")
        spec["ram_gb"], spec["vcpus"] = d["ram_gb"], d["vcpus"]
        # GPU fields move cuda_cores and tensor_cores, which are two of the
        # four capability_score terms, so they reach the rankings too.
        for field, val in (R.derive_gpu(e) or {}).items():
            if spec.get(field) != val:
                notes.append(f"{name}: {field} {spec.get(field)} -> {val}")
            spec[field] = val
    return out, notes


def rank1(gold: str) -> str:
    """The node type recommended first, not the sentence recommending it.

    The rank-1 LINE always changes when a capability number changes, because
    the number is quoted in the justification. That is wording. What matters
    for review is whether the top PICK moved, so the type name is parsed out
    and an infeasible gold reports as no pick at all.
    """
    head = gold.splitlines()[0].strip()
    m = re.match(r"1\.\s+([A-Za-z0-9_]+)", head)
    return m.group(1) if m else "(no feasible pick)"


def main() -> int:
    base = B.captable()
    new, notes = proposed_table(base)

    on_disk = {p.stem: yaml.safe_load(p.read_text())
               for p in sorted(ITEMS.glob("RB*.yaml"))}

    rows, drift = [], []
    idx = 0
    for env in B.ENVIRONMENTS:
        for stem in B.STEMS:
            idx += 1
            iid = f"RB{idx:02d}"
            old_built = B.build(idx, stem, env, base)
            new_built = B.build(idx, stem, env, new)
            disk = on_disk.get(iid)
            if disk is None:
                drift.append(f"{iid}: no file on disk")
            elif disk["gold_spec"] != old_built["gold_spec"]:
                drift.append(f"{iid}: on-disk gold differs from a rebuild "
                             "with the current table")
            rows.append((iid, stem["key"], env[0], old_built, new_built))

    if drift:
        print("FATAL: the item bank is not reproducible from its inputs.")
        for d in drift:
            print(f"  {d}")
        return 1
    print(f"self-check: all {idx} RB items rebuild byte-identical to disk "
          "from the current table")

    changed = [r for r in rows if r[3]["gold_spec"] != r[4]["gold_spec"]]
    flips = [r for r in changed if r[3]["feasible"] != r[4]["feasible"]]
    r1 = [r for r in changed if rank1(r[3]["gold_spec"]) != rank1(r[4]["gold_spec"])]
    checks = [r for r in changed if r[3]["checkers"] != r[4]["checkers"]]

    day = datetime.now(timezone.utc).date().isoformat()
    out = EXPORTS / f"refill_impact_{day}.md"
    L: list[str] = []
    L.append("# Capability-table refill: impact on the reservation golds\n")
    L.append(f"Generated {datetime.now(timezone.utc).isoformat()} · "
             f"capture `{R.latest_capture().name}` · **nothing was written "
             "except this report**\n")
    L.append("## Summary\n")
    L.append("| | count |")
    L.append("|---|---|")
    L.append(f"| RB items total | {len(rows)} |")
    L.append(f"| gold_spec changed | {len(changed)} |")
    L.append(f"| feasibility flipped | {len(flips)} |")
    L.append(f"| rank-1 pick changed | {len(r1)} |")
    L.append(f"| checkers changed | {len(checks)} |")
    L.append("")
    L.append("Every free count is unchanged: only the capability table moved. "
             "CB items are unaffected — their golds are code and never read "
             "this table.\n")

    L.append("## Table fields\n")
    for n in notes:
        L.append(f"- {n}")
    L.append("")

    if flips:
        L.append("## Feasibility flips — a verdict changes, not just wording\n")
        for iid, key, snap, o, n in flips:
            L.append(f"### {iid} · {key} · `{snap}`")
            L.append(f"`feasible: {o['feasible']}` → `{n['feasible']}`\n")
            L.append("```diff")
            L.extend(difflib.unified_diff(
                o["gold_spec"].splitlines(), n["gold_spec"].splitlines(),
                lineterm="", n=1))
            L.append("```\n")

    if r1:
        L.append("## Rank-1 changes — the recommended node type changes\n")
        L.append("| item | stem | snapshot | before | after |")
        L.append("|---|---|---|---|---|")
        for iid, key, snap, o, n in r1:
            L.append(f"| {iid} | {key} | `{snap}` | {rank1(o['gold_spec'])} "
                     f"| {rank1(n['gold_spec'])} |")
        L.append("")

    L.append("## Every changed gold\n")
    for iid, key, snap, o, n in changed:
        tags = []
        if o["feasible"] != n["feasible"]:
            tags.append("FEASIBILITY FLIP")
        if rank1(o["gold_spec"]) != rank1(n["gold_spec"]):
            tags.append("rank-1 changed")
        if o["checkers"] != n["checkers"]:
            tags.append("checkers changed")
        L.append(f"### {iid} · {key} · `{snap}`"
                 + (f" — {', '.join(tags)}" if tags else ""))
        L.append("```diff")
        L.extend(difflib.unified_diff(
            o["gold_spec"].splitlines(), n["gold_spec"].splitlines(),
            lineterm="", n=1))
        L.append("```\n")

    unchanged = [r[0] for r in rows if r not in changed]
    L.append(f"## Unchanged ({len(unchanged)})\n")
    L.append(", ".join(unchanged) or "none")
    L.append("")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L))

    print(f"\n{len(rows)} RB items: {len(changed)} gold(s) change, "
          f"{len(flips)} feasibility flip(s), {len(r1)} rank-1 change(s), "
          f"{len(checks)} checker change(s)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
