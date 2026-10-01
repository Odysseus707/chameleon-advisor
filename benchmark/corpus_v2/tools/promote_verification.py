#!/usr/bin/env python3
"""promote_verification: give `verification_level` a meaning, per item, with evidence.

  python corpus_v2/tools/promote_verification.py
  python corpus_v2/tools/promote_verification.py --apply --live CB06,CB15,CB17,CB27,CB09

D49 recorded the problem: all 136 items carry the string `V0` and "verified"
had been standing in for three claims of very different strength. This assigns
a level per item from evidence gathered this cycle, and records WHICH evidence
beside it.

D49 also said "nothing in the codebase ever writes that field", which is true
and was the wrong question. Nothing writes it; runner.py READS it. See V1
below - checking only for writers is how a documentation field turned out to
be a control field.

THE LEVELS, AND WHAT EACH ONE IS WORTH

  V0  static only. The gold has the right shape - right calls, right kwargs,
      right places - and passes its own checkers. That is the admission gate,
      and on its own it is close to circular.

  V1  RESERVED - DO NOT WRITE IT. `verification_level` is not a label, it is
      a control field: runner.py:80 reads it, and "V1" there means "execute
      this gold against the snapshot and check `v1_expect`". That is the edge
      wing's mechanism. Chameleon items carry `exec_expect` and are executed
      by verify_golds_exec.py, so writing V1 on them activates a grading path
      with no expectations to check - it rejected 20 golds that were fine.

      Stub execution IS still recorded, as `verification.basis:
      stub_execution` with the level left at V0. The evidence belongs in a
      field that describes the item; V1 instructs the runner.

  V2  confirmed against the real testbed this cycle. Split by evidence type,
      because the two wings rest on different facts and pretending otherwise
      would be the overclaim this field exists to prevent:

        live_execution      the gold's own text ran against real Blazar and
                            real Nova and did what its item declares. CB only.
        capability_catalog  every node type the gold names had its capability
                            re-measured from the Chameleon reference API and
                            its existence confirmed against live Blazar. RB.

A NEIGHBOUR'S TEST IS NOT EVIDENCE
Only items actually exercised are promoted. Twenty-six CB golds use the same
reservation idiom as CB06, and not one becomes V2 because CB06 ran: "an item
marked V2 on the strength of a neighbour's test is worse than one left at V0"
was the instruction, and it is right - the whole value of the field is that it
distinguishes what was checked from what was assumed.

WHAT V2 STILL DOES NOT MEAN FOR AN RB ITEM
That its ranked list is correct NOW. Those golds are solved against pinned
snapshots under a deliberate free-now-only convention (D40), and live free
counts change hourly; re-solving against live Blazar would measure what time it
is (R7). capability_catalog says the HARDWARE FACTS the ranking rests on were
re-measured - not that the ordering holds today.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
WING = BENCH / "chameleon_bench"
ITEMS = WING / "data" / "items"
TABLE = WING / "data" / "capability_table.yaml"
LIVE_RESULTS = BENCH / "notebooks" / "live_verification_results.json"

#: capability_source values that count as "re-measured this cycle".
CATALOG_RE = re.compile(r"^reference_api_\d{4}-\d{2}-\d{2}$")


def table() -> dict:
    return yaml.safe_load(TABLE.read_text())["node_types"]


def catalog_confirmed(tbl: dict) -> tuple[set[str], str]:
    ok, src = set(), ""
    for name, spec in tbl.items():
        s = str(spec.get("capability_source") or "")
        if CATALOG_RE.match(s):
            ok.add(name)
            src = s
    return ok, src


def types_named(item: dict, tbl: dict) -> set[str]:
    """Every node type the gold names, ranked or rejected alike.

    Rejections count: "compute_haswell: unknown GB < 180 GB" is a claim ABOUT
    compute_haswell, and an item making it rests on that row being right just
    as much as one recommending it does.
    """
    gold = item.get("gold_spec") or ""
    return {t for t in tbl if t in gold}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--live", default="",
                    help="comma-separated ids whose gold text was executed "
                         "live and verified, e.g. CB06,CB15")
    ap.add_argument("--evidence", default="",
                    help="filename of the live run's report")
    args = ap.parse_args()

    live_ids = {x.strip() for x in args.live.split(",") if x.strip()}
    tbl = table()
    confirmed, cat_src = catalog_confirmed(tbl)

    meta = json.loads(LIVE_RESULTS.read_text()) if LIVE_RESULTS.is_file() else {}
    probe_utc, chi_ver = meta.get("utc", ""), meta.get("python_chi", "")

    counts, rows, unknown = {"V0": 0, "V1": 0, "V2": 0}, [], live_ids.copy()
    for p in sorted(ITEMS.glob("*.yaml")):
        item = yaml.safe_load(p.read_text())
        iid = item["id"]
        unknown.discard(iid)
        level, basis, why = "V0", None, ""

        if item.get("exec_expect"):
            # NOT "V1". `verification_level` is not a label - runner.py:80
            # READS it, and V1 there means "execute this gold against the
            # snapshot and check `v1_expect`". That is the edge wing's
            # mechanism; chameleon items carry `exec_expect` and are executed
            # by verify_golds_exec.py instead. Writing V1 here activated a
            # grading path with no expectations to check and rejected 20 golds
            # that were fine. The stub evidence is recorded in the block
            # instead, where it describes the item rather than instructing the
            # runner.
            level, basis = "V0", "stub_execution"
            why = "executed against the pinned-capture stub (level left V0: "
            why += "V1 is a runner instruction, not a label)"

        if iid in live_ids:
            level, basis = "V2", "live_execution"
            why = "gold text executed against CHI@TACC and verified via the API"
        elif iid.startswith("RB"):
            named = types_named(item, tbl)
            missing = named - confirmed
            if named and not missing:
                level, basis = "V2", "capability_catalog"
                why = (f"all {len(named)} node type(s) named re-measured from "
                       f"{cat_src}, existence confirmed in live Blazar")
            elif named:
                why = (f"not promoted: {', '.join(sorted(missing))} absent "
                       "from the reference API, so its capability is unconfirmed")

        counts[level] += 1
        rows.append((iid, level, basis, why))

        if args.apply:
            text = p.read_text()
            block = f"verification_level: {level}\n"
            if basis:
                block += ("verification:\n"
                          f"  basis: {basis}\n"
                          f"  probe_utc: '{probe_utc}'\n")
                if basis == "live_execution":
                    # Unquoted: yaml.safe_dump renders "1.2.10" bare, and
                    # build_core_items.render() re-emits every item through
                    # safe_dump. Quoting it here makes the two disagree by one
                    # character, so `build_core_items.py check` reports 11
                    # items as needing a rewrite forever.
                    if chi_ver:
                        block += f"  python_chi: {chi_ver}\n"
                    if args.evidence:
                        block += f"  evidence: {args.evidence}\n"
                elif basis == "capability_catalog":
                    block += f"  source: {cat_src}\n"
            new, n = re.subn(
                r"^verification_level: .*\n(?:verification:\n(?:  .*\n)*)?",
                block, text, count=1, flags=re.M)
            if n != 1:
                raise SystemExit(f"{iid}: verification_level not found; refusing "
                                 "to guess where it goes")
            p.write_text(new)

    if unknown:
        raise SystemExit(f"--live named unknown item(s): {sorted(unknown)}")

    for iid, level, basis, why in rows:
        if level != "V0":
            print(f"  {iid:6s} {level}  {basis or '':<19} {why}")
    held = [r for r in rows if r[1] == "V0" and r[3]]
    if held:
        print(f"\nheld at V0 with a reason ({len(held)}):")
        for iid, _, _, why in held[:6]:
            print(f"  {iid:6s} {why}")
        if len(held) > 6:
            print(f"  ... and {len(held) - 6} more")
    print(f"\nV0 {counts['V0']} · V1 {counts['V1']} · V2 {counts['V2']} "
          f"of {sum(counts.values())} items")
    if not args.apply:
        print("report only; pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
