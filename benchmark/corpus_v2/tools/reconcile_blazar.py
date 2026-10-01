#!/usr/bin/env python3
"""reconcile_blazar: the capability table's EXISTENCE claims vs live Blazar.

  python corpus_v2/tools/reconcile_blazar.py

Read-only. GETs only. Creates no lease, writes no snapshot, spends no SUs.
Writes exports/blazar_reconcile_<date>.md and nothing else.

WHAT THIS CHECKS, AND WHY IT IS NOT THE SAME QUESTION AS THE REFILL
The reference API answers "what is this hardware", and the refill used it for
exactly that. Blazar answers "does it exist here, and can you book it", which
the catalog cannot: a decommissioned node can linger in a hardware catalog, and
a node in maintenance is fully described and completely unbookable.

So this compares three things the table asserts and Blazar is authoritative for:

  sites       R6. A type at the wrong site is wrong in a way waiting cannot fix.
  node_count  the per-site tallies the table carries.
  reservable  a host Blazar will not let you book is not capacity, and reporting
              it as free is the failure that hands a user an unsubmittable spec.

FINDINGS ARE FINDINGS, NEVER A REPIN
Under R7 live state is evidence about the testbed and never a gold. The golds
are solved against the pinned 2026-09-04 capture; if live disagrees, that is a
fact about the capture and the fix is a NEW capture with a new date, never an
edit to the old one. This tool therefore reports and changes nothing at all.
compute_haswell is the standing example: 27 hosts in the capture, absent from
live Blazar on 2026-09-05, still in the table because the table describes the
capture.

CREDENTIALS
Sourced by advisor.availability.blazar.load_rc, which runs each openrc in a
subshell with stdin closed so a password-prompting file fails fast instead of
hanging, and lets only OS_* variables cross back. Nothing from the environment
is printed here - not the project, not the credential id, not an endpoint that
embeds one.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
ROOT = BENCH.parent
TABLE = BENCH / "chameleon_bench" / "data" / "capability_table.yaml"
EXPORTS = BENCH / "exports"
RC_GLOB = str(ROOT / "credentials" / "app-cred-*-openrc.sh")

sys.path.insert(0, str(ROOT / "chi-edge-advisor"))

#: The two sites this wing grades. Other openrc files in credentials/ point at
#: CHI@Edge, KVM@TACC, NCAR, NRP and NU; probing them would cost time to
#: produce rows no item grades against.
GRADED = {"CHI@TACC", "CHI@UC"}


def main() -> int:
    from advisor.availability.blazar import fetch_sites   # noqa: E402

    probed = datetime.now(timezone.utc)
    table = yaml.safe_load(TABLE.read_text())["node_types"]

    live: dict[str, dict[str, dict]] = {}
    errors = []
    for block in fetch_sites(rc_glob=RC_GLOB, sites=GRADED):
        site = block["site"]
        if block["error"]:
            errors.append(f"{site}: {block['error']}")
            continue
        for n in block["nodes"]:
            e = live.setdefault(n["node_type"], {}).setdefault(
                site, {"total": 0, "reservable": 0, "free": 0})
            e["total"] += 1
            e["reservable"] += bool(n["reservable"])
            e["free"] += n["status"] == "free"

    L = ["# Live Blazar vs the capability table\n",
         f"Probed {probed.isoformat()} · read-only, no lease created, 0 SUs\n"]
    if errors:
        L.append("## Probe errors\n")
        L.extend(f"- {e}" for e in errors)
        L.append("")

    gone, appeared, count_drift, unbookable = [], [], [], []

    for name in sorted(table):
        spec = table[name]
        claimed = {s: c for s, c in (spec.get("sites") or {}).items()
                   if s in GRADED}
        seen = live.get(name, {})
        if claimed and not seen:
            gone.append((name, claimed))
            continue
        for site, count in claimed.items():
            got = seen.get(site)
            if not got:
                gone.append((name, {site: count}))
                continue
            if got["total"] != count:
                count_drift.append((name, site, count, got["total"]))
            if got["reservable"] < got["total"]:
                unbookable.append(
                    (name, site, got["total"] - got["reservable"], got["total"]))
        for site in seen:
            if site not in claimed:
                appeared.append((name, site, seen[site]["total"]))

    for name in sorted(set(live) - set(table)):
        for site, got in live[name].items():
            appeared.append((name, site, got["total"]))

    L.append("## Summary\n")
    L.append("| check | result |")
    L.append("|---|---|")
    L.append(f"| types in the table | {len(table)} |")
    L.append(f"| types seen live | {len(live)} |")
    L.append(f"| claimed but ABSENT live | {len(gone)} |")
    L.append(f"| live but absent from the table | {len(appeared)} |")
    L.append(f"| node-count drift | {len(count_drift)} |")
    L.append(f"| types with unbookable hosts | {len(unbookable)} |")
    L.append("")

    def section(title, rows, header, fmt):
        L.append(f"## {title}\n")
        if not rows:
            L.append("None.\n")
            return
        L.append(header)
        L.append("|" + "---|" * (header.count("|") - 1))
        L.extend(fmt(r) for r in rows)
        L.append("")

    section("Claimed by the table, ABSENT from live Blazar (R6/R7)", gone,
            "| node_type | claimed |",
            lambda r: f"| `{r[0]}` | {r[1]} |")
    section("Present live, absent from the table", appeared,
            "| node_type | site | live hosts |",
            lambda r: f"| `{r[0]}` | {r[1]} | {r[2]} |")
    section("Node-count drift", count_drift,
            "| node_type | site | table | live |",
            lambda r: f"| `{r[0]}` | {r[1]} | {r[2]} | {r[3]} |")
    section("Hosts Blazar will not let you book (R5)", unbookable,
            "| node_type | site | unbookable | of total |",
            lambda r: f"| `{r[0]}` | {r[1]} | {r[2]} | {r[3]} |")

    L.append("## What was NOT done\n")
    L.append("Nothing here was written back. Under R7 a live probe is evidence "
             "about the testbed and never a gold: the golds are solved against "
             "the pinned 2026-09-04 capture, and if live disagrees the fix is a "
             "new capture with a new date, not an edit to the old one.\n")

    EXPORTS.mkdir(parents=True, exist_ok=True)
    out = EXPORTS / f"blazar_reconcile_{probed.date().isoformat()}.md"
    out.write_text("\n".join(L))

    print(f"types: table {len(table)}, live {len(live)} | absent live "
          f"{len(gone)} | unlisted {len(appeared)} | count drift "
          f"{len(count_drift)} | unbookable {len(unbookable)}")
    if errors:
        print("probe errors: " + "; ".join(errors))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
