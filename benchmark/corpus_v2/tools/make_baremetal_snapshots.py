#!/usr/bin/env python3
"""make_baremetal_snapshots: a live Blazar capture -> graded snapshot files.

  python corpus_v2/tools/make_baremetal_snapshots.py --capture <raw.json>

WHAT A SNAPSHOT IS
The recorded reservable state of one site at one instant. Every reservation gold
is solved against one, so it is measurement, not configuration: a snapshot that
quietly changed would move verdicts with no item, prompt or checker changing.
Hence `_meta.source_sha256` and `_meta.SYNTHETIC`, and hence Level 1 parity
watching snapshots/*.json in every wing.

REAL vs DERIVED
`SYNTHETIC: false` means these hosts and states were read from Blazar. Derived
variants (scarce / blackout / inversion / abundant) are perturbations of a real
capture and carry `SYNTHETIC: true` plus `derived_from`. The two must never be
confusable - the edge wing flags its own synthetic default for the same reason
(decision D13).

WHY node_type AND NOT device_type
CHI@Edge reserves devices; the general testbed reserves hosts, and Blazar itself
calls the field `node_type`. checks._snapshot_counts reads either. Renaming real
hosts to "devices" to match the older wing would put a wrong word in the
measurement to save a line of parsing.

KVM@TACC IS CAPTURED BUT NOT GRADED
Its node_type values are hypervisor classes - compute, QEMU, gpu - not reservable
types, because KVM launches on flavors and does not reserve hosts at all. "Is a
node of type X free" has no answer there, so no reservation item grades against
it. The file is still written: it documents the site, and the absence is then a
recorded fact rather than a gap someone later mistakes for an oversight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
SNAPSHOTS = BENCH / "chameleon_bench" / "data" / "snapshots"

#: site -> (filename stem, graded?)
SITES = {
    "CHI@UC":   ("baremetal_uc", True),
    "CHI@TACC": ("baremetal_tacc", True),
    "KVM@TACC": ("kvm_tacc", False),
}

#: Per-host fields carried through. The capability ones (ram_gb, vcpus,
#: gpu_count, gpu_model) are Blazar's own and are kept for CROSS-CHECKING the
#: hand-authored capability table, never as a substitute for it: mixing measured
#: and vendor-specified facts in one table is how you stop being able to say
#: which is which.
NODE_FIELDS = ("node_type", "status", "reservable", "uid",
               "available_hours", "next_free_utc",
               "ram_gb", "vcpus", "gpu_count", "gpu_model")


def reshape(site_block: dict, captured: str, src_sha: str, graded: bool) -> dict:
    site = site_block["site"]
    nodes = []
    for n in site_block["nodes"]:
        rec = {"device_name": n.get("name"), "free": n.get("status") == "free"}
        rec.update({f: n.get(f) for f in NODE_FIELDS})
        nodes.append(rec)
    nodes.sort(key=lambda r: (r["node_type"] or "", r["device_name"] or ""))

    types = sorted({n["node_type"] for n in nodes if n["node_type"]})
    free = {t: sum(1 for n in nodes if n["node_type"] == t and n["free"])
            for t in types}
    total = {t: sum(1 for n in nodes if n["node_type"] == t) for t in types}

    meta = {
        "SYNTHETIC": False,
        "variant": "base",
        "site": site,
        "recorded": captured,
        "source_sha256": src_sha,
        "resource_kind": "host",
        "blazar": site_block.get("blazar"),
        "graded": graded,
        "schema": ["device_name", "free", *NODE_FIELDS],
        "node_type_totals": total,
        "node_type_free": free,
        "note": ("Recorded Chameleon bare-metal state via Blazar os-hosts. "
                 "Real data."),
    }
    if not graded:
        meta["note"] = (
            "Recorded KVM@TACC state via Blazar os-hosts. Real data, but NOT "
            "graded against: node_type here is a hypervisor class (compute, "
            "QEMU, gpu), not a reservable type. KVM launches on flavors and "
            "does not reserve hosts, so per-type free counts do not answer any "
            "reservation question. Kept as documentation of the site.")
    return {"_meta": meta, "devices": nodes}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capture", required=True, type=Path,
                    help="raw probe_availability.py --json --nodes output")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw_bytes = args.capture.read_bytes()
    src_sha = hashlib.sha256(raw_bytes).hexdigest()
    raw = json.loads(raw_bytes)
    captured = raw["generated_utc"]
    day = captured[:10]

    seen = {b["site"] for b in raw["sites"]}
    unknown = seen - set(SITES)
    if unknown:
        raise SystemExit(f"capture contains unmapped site(s) {sorted(unknown)}; "
                         "add them to SITES or narrow the --rc glob.")

    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    for block in raw["sites"]:
        stem, graded = SITES[block["site"]]
        out = SNAPSHOTS / f"{stem}_{day}.json"
        doc = reshape(block, captured, src_sha, graded)
        text = json.dumps(doc, indent=1, sort_keys=False) + "\n"
        n = len(doc["devices"])
        nfree = sum(1 for d in doc["devices"] if d["free"])
        flag = "graded" if graded else "NOT graded"
        print(f"  {out.name:<34} {n:>4} hosts, {nfree:>3} free  [{flag}]")
        if not args.dry_run:
            if out.exists() and out.read_text() == text:
                continue                      # R5: a no-op writes nothing
            out.write_text(text)

    # The raw capture is kept beside the reshaped files: source_sha256 above is
    # only checkable against something.
    keep = SNAPSHOTS / f"_capture_{day}.json"
    if not args.dry_run and (not keep.exists() or keep.read_bytes() != raw_bytes):
        keep.write_bytes(raw_bytes)
    print(f"  {keep.name:<34} raw capture, sha256 {src_sha[:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
