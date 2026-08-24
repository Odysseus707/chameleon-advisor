#!/usr/bin/env python3
"""Independently re-derive the reservation golds and check they hold up.

This is NOT the human audit. It is the machine half: it re-reads every claim a
gold makes straight from the snapshot JSON, without calling the solver that
wrote it, so a bug in the solver cannot excuse itself. Human review of a
stratified sample is still owed and is tracked separately.

Three things are checked.

  1. COUNT CLAIMS. Every "N of M free" string in a gold is re-counted from the
     snapshot. A gold that misreports availability is worse than no gold.
  2. PERTURBATION SANITY. A stem whose gold never changes across the six
     environments is a broken item, not a hard one: it cannot distinguish a
     system that reads live state from one that does not, which is the whole
     point of the suite.
  3. TRAP HONESTY. Nothing in a gold's recommended list may be a type it also
     lists as not recommended.

  python tools/audit_golds.py            # full audit
  python tools/audit_golds.py --sample 25
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness.checks import extract_ranked_types  # noqa: E402

CLAIM = re.compile(r"^\s*\d+\.\s*(\S+)\s*-\s*(\d+) of (\d+) free", re.MULTILINE)


def snapshot_counts(name: str) -> dict:
    """Count free/total per type straight from the JSON. No solver involved."""
    devices = json.loads((ROOT / "snapshots" / f"{name}.json").read_text())["devices"]
    out = defaultdict(lambda: {"free": 0, "total": 0})
    for d in devices:
        out[d["device_type"]]["total"] += 1
        if d["status"] == "free":
            out[d["device_type"]]["free"] += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", type=int, default=0,
                    help="audit a stratified random sample of this many items")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    items = []
    for p in sorted((ROOT / "items").glob("R*.yaml")):
        items.append(yaml.safe_load(p.read_text()))
    if not items:
        raise SystemExit("no R*.yaml items; run tools/build_reservation_items.py")

    audited = items
    if args.sample:
        # Stratify by stem so the sample cannot land entirely in easy items.
        by_stem = defaultdict(list)
        for it in items:
            by_stem[it["stem"]].append(it)
        rng, audited = random.Random(args.seed), []
        per = max(1, args.sample // len(by_stem))
        for stem in sorted(by_stem):
            audited += rng.sample(by_stem[stem], min(per, len(by_stem[stem])))
        audited = audited[:args.sample]

    caches, bad_counts, bad_traps, claims = {}, [], [], 0
    for it in audited:
        snap = it["snapshot"]
        if snap not in caches:
            caches[snap] = snapshot_counts(snap)
        counts = caches[snap]
        for dtype, free, total in CLAIM.findall(it["gold_spec"]):
            claims += 1
            real = counts.get(dtype, {"free": 0, "total": 0})
            if (int(free), int(total)) != (real["free"], real["total"]):
                bad_counts.append(
                    f"{it['id']} {dtype}: gold says {free}/{total}, "
                    f"snapshot says {real['free']}/{real['total']}")
        recommended = set(extract_ranked_types(it["gold_spec"]))
        rejected = set(re.findall(r"^- (\S+):", it["gold_spec"], re.MULTILINE))
        overlap = recommended & rejected
        if overlap:
            bad_traps.append(f"{it['id']}: {sorted(overlap)} both recommended "
                             "and rejected")

    # Perturbation sanity, always over the FULL set: a sample cannot show that a
    # stem's gold moves across environments.
    by_stem = defaultdict(dict)
    for it in items:
        picks = extract_ranked_types(it["gold_spec"])
        by_stem[it["stem"]][it["snapshot"]] = picks[0] if picks else "(none)"
    inert = [s for s, envs in by_stem.items() if len(set(envs.values())) == 1]

    print(f"Audited {len(audited)} of {len(items)} items, {claims} count claims\n")
    print(f"1. count claims re-derived from snapshots   "
          f"{claims - len(bad_counts)}/{claims} agree")
    for b in bad_counts[:10]:
        print(f"     x {b}")
    print(f"2. stems whose gold moves across environments "
          f"{len(by_stem) - len(inert)}/{len(by_stem)}")
    for s in inert:
        print(f"     x {s}: same top pick in all "
              f"{len(by_stem[s])} environments -> cannot test state-sensitivity")
    print(f"3. no type both recommended and rejected     "
          f"{len(audited) - len(bad_traps)}/{len(audited)} clean")
    for b in bad_traps[:10]:
        print(f"     x {b}")

    spread = Counter()
    for s, envs in by_stem.items():
        spread[len(set(envs.values()))] += 1
    print("\nDistinct top picks per stem across 6 environments: "
          + ", ".join(f"{k} pick(s): {v} stems" for k, v in sorted(spread.items())))

    failed = bool(bad_counts or bad_traps)
    print("\nAUDIT " + ("FAILED" if failed else "PASSED")
          + ".  Human review of a stratified sample is still outstanding.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
