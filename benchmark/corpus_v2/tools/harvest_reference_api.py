#!/usr/bin/env python3
"""harvest_reference_api: per-node hardware facts from the Chameleon reference API.

  python corpus_v2/tools/harvest_reference_api.py            # write the capture
  python corpus_v2/tools/harvest_reference_api.py --dry-run  # print, write nothing

WHY THIS EXISTS
The capability table's ram_gb and vcpus came from Blazar, which reports
`memory_mb` and `vcpus` per host only when Ironic happened to record them. It
did so for 102 of 345 TACC hosts, which is why 17 of 29 node types carry null
and why, under R4, those types fail every minimum they are tested against - for
lack of data, not for lack of capability.

The reference API (https://api.chameleoncloud.org, Grid'5000 schema) is the
testbed's own hardware catalog. It answers for 100% of the nodes at both graded
sites, needs no credentials, costs no SUs, and is a DIFFERENT KIND OF SOURCE
from Blazar: a catalog of what the hardware IS, not a report of what is free.
Blazar remains authoritative for existence, reservability and free counts; this
is authoritative for capability. Neither substitutes for the other, and the
table labels which fields came from which.

WHAT IT RECORDS, AND WHAT IT REFUSES TO DECIDE
Raw measurements only: ram_size, smt_size, smp_size, the CPU model string, GPU
count and model, per node, aggregated into a distribution per node type. It
deliberately does NOT collapse smt_size into a "vcpus" number, because that
collapse needs an SMT assumption that varies by vendor (x86 is 2 threads per
core, the Ampere Altra in compute_arm64 is 1) and an assumption is not a
measurement. The distribution is preserved so the caller can see when one type
is not one machine.

INTRA-TYPE VARIANCE IS REAL AND IS NOT ALL THE SAME KIND
Two different things show up as a spread:

  HETEROGENEOUS  compute_gigaio really is 6 Intel nodes and 8 AMD ones; the
                 type genuinely spans two machines and a scalar hides it.
  UNDER-REPORTED one compute_cascadelake node reports smt_size 32 where the
                 other 23 report 64, all with the same Gold 6242 CPU. That is
                 a thin record, not a smaller machine.

`cpu_models` distinguishes them: one model with a spread is under-reporting,
two models is heterogeneity. Callers get counts, so a 1-of-24 outlier is
visible as one.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
OUT_DIR = BENCH / "chameleon_bench" / "data" / "reference_api"

BASE = "https://api.chameleoncloud.org"
TIMEOUT = 30

#: reference-API site uid -> the site name the capability table and Blazar use.
#: Only the two GRADED sites. edge/kvm/nrp/ncar/nu exist upstream and are out of
#: scope for this wing: KVM reserves flavors rather than hosts, so per-type
#: capability does not answer a reservation question there (see the KVM note in
#: make_baremetal_snapshots.py).
SITES = {"tacc": "CHI@TACC", "uc": "CHI@UC"}


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        return json.load(r)


def fetch_nodes() -> tuple[list[dict], list[str]]:
    """Every node record at both graded sites, plus the URLs they came from."""
    nodes, urls = [], []
    for uid, site in SITES.items():
        cu = f"{BASE}/sites/{uid}/clusters.json"
        urls.append(cu)
        for cluster in _get(cu).get("items", []):
            cid = cluster.get("uid")
            if not cid:
                continue
            nu = f"{BASE}/sites/{uid}/clusters/{cid}/nodes.json"
            urls.append(nu)
            for node in _get(nu).get("items", []):
                node["_site"] = site
                nodes.append(node)
    return nodes, urls


def aggregate(nodes: list[dict]) -> dict:
    """node_type -> distributions of every raw field, with counts."""
    out: dict[str, dict] = {}
    for n in nodes:
        t = n.get("node_type")
        if not t:
            continue
        arch, proc = n.get("architecture") or {}, n.get("processor") or {}
        gpu, mem = n.get("gpu") or {}, n.get("main_memory") or {}
        e = out.setdefault(t, {
            "node_count": 0,
            "sites": collections.Counter(),
            "ram_gib": collections.Counter(),
            "smt_size": collections.Counter(),
            "smp_size": collections.Counter(),
            "platform_type": collections.Counter(),
            "cpu_models": collections.Counter(),
            "gpu_count": collections.Counter(),
            "gpu_models": collections.Counter(),
        })
        e["node_count"] += 1
        e["sites"][n["_site"]] += 1
        if mem.get("ram_size"):
            # GiB, floored: 192 GiB installed reads 192, and a node reporting
            # 191.9 must not round up into a minimum it does not meet.
            e["ram_gib"][int(mem["ram_size"] // 1024**3)] += 1
        for key in ("smt_size", "smp_size", "platform_type"):
            if arch.get(key):
                e[key][arch[key]] += 1
        if proc.get("model"):
            e["cpu_models"][proc["model"]] += 1
        if gpu.get("gpu"):
            if gpu.get("gpu_count"):
                e["gpu_count"][gpu["gpu_count"]] += 1
            if gpu.get("gpu_model"):
                e["gpu_models"][gpu["gpu_model"]] += 1
    # Counters -> plain dicts, so the JSON round-trips as ordinary mappings.
    return {t: {k: (dict(v) if isinstance(v, collections.Counter) else v)
                for k, v in e.items()} for t, e in sorted(out.items())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    probed = datetime.now(timezone.utc).isoformat()
    nodes, urls = fetch_nodes()
    types = aggregate(nodes)

    doc = {
        "_meta": {
            "source": "chameleon_reference_api",
            "base": BASE,
            "urls": urls,
            "probed_utc": probed,
            "sites": list(SITES.values()),
            "node_records": len(nodes),
            "note": ("Hardware catalog, NOT reservation state. Distributions "
                     "are preserved verbatim; no scalar is chosen here and no "
                     "SMT assumption is applied. See the module docstring for "
                     "why smt_size is not written as vcpus."),
        },
        "node_types": types,
    }

    for t, e in types.items():
        spread = [k for k in ("ram_gib", "smt_size") if len(e[k]) > 1]
        flag = f"  SPREAD in {'+'.join(spread)}" if spread else ""
        print(f"  {t:<24} n={e['node_count']:<4} ram={sorted(e['ram_gib'])} "
              f"smt={sorted(e['smt_size'])} cpus={len(e['cpu_models'])}{flag}")
    print(f"\n{len(nodes)} node record(s), {len(types)} node type(s), "
          f"probed {probed}")

    day = probed[:10]
    out = OUT_DIR / f"reference_api_{day}.json"
    text = json.dumps(doc, indent=1, sort_keys=False) + "\n"
    if args.dry_run:
        print(f"[dry run] would write {out}")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.read_text() == text:
        print(f"unchanged: {out}")      # a no-op writes nothing
    else:
        out.write_text(text)
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
