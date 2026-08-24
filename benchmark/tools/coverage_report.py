#!/usr/bin/env python3
"""Measure artifact coverage of CHI@Edge hardware. The v5 result, in one table.

Answers one question: of the device types actually live on CHI@Edge, how many
does the Trovi corpus document at all? Everything in
audit/advisor_architecture_decision.md is generated from this, so the memo's
figures and this output must agree exactly.

Sources, all read-only:
  compendium/trovi_records.json              full corpus, 460 records
  compendium/advisor_artifact_ranking.xlsx   triaged + scored, 205 artifacts
  snapshots/edge_2026-08-13.json             recorded live inventory
  capability_table.yaml                      which types an artifact covers

  python tools/coverage_report.py            # table to stdout
  python tools/coverage_report.py --json     # machine-readable

The compendium is gitignored (1.4 MB of scraped records), so a fresh clone
reports what it can and says which sources were missing rather than dying.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TROVI = ROOT / "compendium" / "trovi_records.json"
RANKING = ROOT / "compendium" / "advisor_artifact_ranking.xlsx"
SNAPSHOT = ROOT / "snapshots" / "edge_2026-08-13.json"
CAPTABLE = ROOT / "capability_table.yaml"

EDGE_HW = re.compile(
    r"chi@edge|raspberry|jetson|coral|edge device|add_device_reservation|"
    r"device_profiles", re.I)
KEYWORDS = ("jetson", "coral", "xavier", "orin",
            "raspberry pi 5", "raspberry pi 4", "chi@edge")


def scan_trovi() -> dict | None:
    if not TROVI.is_file():
        return None
    records = json.loads(TROVI.read_text())
    hits, kw = [], Counter()
    for r in records:
        blob = " ".join(str(r.get(k) or "") for k in
                        ("title", "short_description", "long_description"))
        tags = " ".join(str(t) for t in (r.get("tags") or []))
        if EDGE_HW.search(blob + " " + tags):
            hits.append(r)
            low = blob.lower()
            for k in KEYWORDS:
                if k in low:
                    kw[k] += 1
    return {"total": len(records), "edge_mentions": len(hits),
            "keywords": dict(kw),
            "titles": [str(r.get("title")) for r in hits]}


def scan_ranking() -> dict | None:
    if not RANKING.is_file():
        return None
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None
    ws = load_workbook(RANKING, read_only=True)["Ranked Artifacts"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) for h in rows[0]]
    recs = [dict(zip(hdr, r)) for r in rows[1:] if r and r[0] is not None]
    fam = Counter(str(r.get("api_family_detected")) for r in recs)
    edge = [r for r in recs if str(r.get("api_family_detected")).strip() == "edge"]
    return {"total": len(recs), "api_family": dict(fam), "edge": len(edge),
            "edge_artifacts": [(str(r.get("artifact_id")),
                                str(r.get("node_types_observed"))) for r in edge]}


def scan_hardware() -> dict:
    devices = json.loads(SNAPSHOT.read_text())["devices"]
    table = yaml.safe_load(CAPTABLE.read_text())["device_types"]
    per = {}
    for d in devices:
        c = per.setdefault(d["device_type"], Counter())
        c[d["status"]] += 1
        c["total"] += 1
    out = []
    for t, c in sorted(per.items(), key=lambda kv: -kv[1]["total"]):
        spec = table.get(t, {})
        out.append({
            "device_type": t, "free": c["free"], "busy": c["busy"],
            "down": c["down"], "total": c["total"],
            "accelerator": spec.get("accelerator", "?"),
            "covered_by": spec.get("covered_by") or [],
        })
    return {"types": out, "devices": len(devices)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    hw, trovi, rank = scan_hardware(), scan_trovi(), scan_ranking()
    covered = [t for t in hw["types"] if t["covered_by"]]
    uncovered = [t for t in hw["types"] if not t["covered_by"]]
    accel_uncov = [t for t in uncovered if t["accelerator"] != "none"]
    dev_covered = sum(t["total"] for t in covered)

    if args.json:
        print(json.dumps({"hardware": hw, "trovi": trovi, "ranking": rank,
                          "covered_types": len(covered),
                          "uncovered_types": len(uncovered)}, indent=2))
        return 0

    print("CHI@Edge artifact coverage\n" + "=" * 66)
    if trovi:
        print(f"Trovi records total                     {trovi['total']:>5}")
        print(f"  mentioning edge hardware at all       {trovi['edge_mentions']:>5}")
        for k in ("jetson", "coral", "xavier", "orin", "raspberry pi 5"):
            print(f"    ...mentioning {k:<22}{trovi['keywords'].get(k, 0):>5}")
    else:
        print("Trovi corpus not present (compendium/ is gitignored)")
    if rank:
        print(f"Ranked artifacts                        {rank['total']:>5}")
        print(f"  api_family = edge                     {rank['edge']:>5}")
        for aid, nodes in rank["edge_artifacts"]:
            print(f"    {aid[:38]:<38} {nodes[:22]}")
    else:
        print("Ranking workbook not present")

    print("\nLive CHI@Edge inventory vs artifact coverage")
    print(f"{'device_type':<30}{'free':>5}{'busy':>5}{'down':>5}{'total':>6}"
          f"  {'accel':<8} coverage")
    for t in hw["types"]:
        cov = ",".join(t["covered_by"]) if t["covered_by"] else "NONE"
        print(f"{t['device_type']:<30}{t['free']:>5}{t['busy']:>5}{t['down']:>5}"
              f"{t['total']:>6}  {t['accelerator']:<8} {cov}")

    n = len(hw["types"])
    print(f"\nTypes covered by >=1 artifact   {len(covered)}/{n} "
          f"({len(covered) / n:.0%})")
    print(f"Devices of a covered type       {dev_covered}/{hw['devices']} "
          f"({dev_covered / hw['devices']:.0%})")
    print(f"Accelerator types uncovered     {len(accel_uncov)}/"
          f"{sum(1 for t in hw['types'] if t['accelerator'] != 'none')}"
          f"  -> {', '.join(t['device_type'] for t in accel_uncov)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
