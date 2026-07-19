#!/usr/bin/env python3
"""probe_availability.py -- FIRST deliverable.

Empirically determine whether the Chameleon *reference API*
(https://api.chameleoncloud.org) reflects live CHI@Edge reservation state, or
only static hardware inventory. The rest of chi-edge-advisor must work
regardless of which backend supplies live state; this probe decides whether the
ReferenceApiBackend can ever be that source.

Method (all against the live API, nothing assumed):
  1. Reachability: is the reference API up and does the `edge` site exist?
  2. Inventory: walk /sites/edge -> clusters -> nodes. How many CHI@Edge
     devices does the reference API actually expose?
  3. Target device: try to locate a specific edge device type
     (raspberrypi4-64, used by every seeded artifact) in that inventory.
  4. Schema: inspect a reference *node* record for any reservation/availability/
     status/lease/state fields -- the fields that would be required to express
     live state.
  5. Live endpoints: probe undocumented candidate live-status paths.
  6. Verdict: STATIC-ONLY vs LIVE-AWARE, with the evidence that decided it.

Run:  python probe_availability.py [--machine-type raspberrypi4-64] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

# Allow running as a plain script from the repo root.
sys.path.insert(0, __file__.rsplit("/", 1)[0])

from advisor.availability.reference_api import (  # noqa: E402
    LIVE_STATUS_CANDIDATES,
    ReferenceApiBackend,
)
from advisor.config import settings  # noqa: E402
from advisor.http_util import get_json  # noqa: E402
from advisor.logging_utils import RunLogger  # noqa: E402

RESERVATION_KEYS = ("reserv", "avail", "free", "status", "lease", "state", "booking")

# A baremetal site whose node schema we sample to characterize what the
# reference API models in general (the edge site itself exposes no nodes).
_SCHEMA_SAMPLE_SITE = "tacc"


def _sample_reference_node_schema(base: str) -> Dict[str, Any]:
    """Fetch one node from a baremetal site and inspect its schema shape."""
    out: Dict[str, Any] = {"keys": [], "reservation_like_keys": [], "sampled": None}
    clusters = get_json(f"{base}/sites/{_SCHEMA_SAMPLE_SITE}/clusters.json")
    if not clusters.ok or not clusters.json.get("items"):
        return out
    cuid = clusters.json["items"][0]["uid"]
    nodes = get_json(
        f"{base}/sites/{_SCHEMA_SAMPLE_SITE}/clusters/{cuid}/nodes.json"
    )
    if not nodes.ok or not nodes.json.get("items"):
        return out
    nuid = nodes.json["items"][0]["uid"]
    node = get_json(
        f"{base}/sites/{_SCHEMA_SAMPLE_SITE}/clusters/{cuid}/nodes/{nuid}.json"
    )
    if not node.ok or not isinstance(node.json, dict):
        return out
    keys = sorted(node.json.keys())
    out["keys"] = keys
    out["reservation_like_keys"] = [
        k for k in keys if any(t in k.lower() for t in RESERVATION_KEYS)
    ]
    out["sampled"] = f"{_SCHEMA_SAMPLE_SITE}/{cuid}/{nuid}"
    return out


def run_probe(machine_type: str = "raspberrypi4-64") -> Dict[str, Any]:
    base = settings.reference_api_base.rstrip("/")
    site = settings.edge_site_uid
    backend = ReferenceApiBackend(base=base, site=site)
    result: Dict[str, Any] = {"base": base, "edge_site": site, "machine_type": machine_type}

    # 1. Reachability -----------------------------------------------------
    site_res = get_json(f"{base}/sites/{site}.json")
    result["api_reachable"] = site_res.ok
    result["edge_site_exists"] = bool(
        site_res.ok and isinstance(site_res.json, dict) and site_res.json.get("uid") == site
    )

    # 2. Inventory: how many edge devices does the reference API expose? ---
    clusters = get_json(f"{base}/sites/{site}/clusters.json")
    result["edge_cluster_count"] = (
        clusters.json.get("total") if clusters.ok and isinstance(clusters.json, dict) else None
    )
    edge_devices = backend.list_devices() if result["edge_site_exists"] else []
    result["edge_device_count"] = len(edge_devices)
    result["edge_device_uids"] = [d.device_uid for d in edge_devices[:20]]

    # 3. Target device of the requested machine_type ----------------------
    target = [d for d in edge_devices if d.machine_type == machine_type]
    result["target_devices_found"] = len(target)

    # 4. Reference node schema: any reservation-like fields at all? --------
    result["node_schema"] = _sample_reference_node_schema(base)

    # 5. Live-status endpoint probe --------------------------------------
    result["live_probe"] = backend.probe_live_status()

    # 6. Verdict ----------------------------------------------------------
    has_live_endpoint = result["live_probe"]["live_endpoint"] is not None
    schema_has_reservation = bool(result["node_schema"]["reservation_like_keys"])
    exposes_edge_devices = result["edge_device_count"] > 0

    if has_live_endpoint or schema_has_reservation:
        verdict = "LIVE-AWARE"
    else:
        verdict = "STATIC-ONLY"
    result["verdict"] = verdict
    result["reference_exposes_edge_inventory"] = exposes_edge_devices
    result["live_state_source_required"] = (
        "blazar" if verdict == "STATIC-ONLY" else "reference_api"
    )
    return result


def _fmt(res: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("=" * 70)
    L.append("  chi-edge-advisor :: reference-API availability probe")
    L.append("=" * 70)
    L.append(f"  reference API base : {res['base']}")
    L.append(f"  edge site          : {res['edge_site']}")
    L.append(f"  target machine_type: {res['machine_type']}")
    L.append("-" * 70)
    L.append("  1. REACHABILITY")
    L.append(f"     api reachable         : {res['api_reachable']}")
    L.append(f"     edge site exists      : {res['edge_site_exists']}")
    L.append("  2. INVENTORY (reference API)")
    L.append(f"     edge clusters         : {res['edge_cluster_count']}")
    L.append(f"     edge devices exposed  : {res['edge_device_count']}")
    L.append("  3. TARGET DEVICE")
    L.append(
        f"     '{res['machine_type']}' devices in reference API : "
        f"{res['target_devices_found']}"
    )
    L.append("  4. NODE SCHEMA (sampled from a baremetal site)")
    sch = res["node_schema"]
    L.append(f"     sampled node          : {sch['sampled']}")
    L.append(f"     reservation-like keys : {sch['reservation_like_keys'] or 'NONE'}")
    L.append("  5. LIVE-STATUS ENDPOINT PROBE")
    for c in res["live_probe"]["candidates"]:
        L.append(f"     [{c['status']:>3}] {'ok' if c['ok'] else '--'}  {c['path']}")
    L.append(f"     discovered live endpoint : {res['live_probe']['live_endpoint']}")
    L.append("=" * 70)
    L.append(f"  VERDICT: reference API is {res['verdict']}")
    L.append("=" * 70)
    if res["verdict"] == "STATIC-ONLY":
        L.append("  The reference API does NOT reflect live reservation state.")
        if not res["reference_exposes_edge_inventory"]:
            L.append(
                "  Moreover it exposes NO CHI@Edge device inventory at all "
                "(edge site has 0 clusters / 0 nodes)."
            )
        L.append("  Evidence:")
        L.append("    - no live-status endpoint responded")
        L.append("    - node records carry only static hardware fields")
        L.append("      (no reservation/availability/lease/state fields)")
        L.append("")
        L.append("  => Live availability MUST come from Blazar via python-chi.")
        L.append("     Set AVAILABILITY_BACKEND=blazar for live state.")
        L.append("     ReferenceApiBackend is usable only for static identity.")
    else:
        L.append("  The reference API appears to expose live state; verify the")
        L.append("  discovered endpoint before trusting it as authoritative.")
    L.append("=" * 70)
    return "\n".join(L)


def probe_blazar(machine_type: str = "raspberrypi4-64") -> Dict[str, Any]:
    """Query Blazar via python-chi for live device state.

    Returns a result dict; 'error' key is set (and others absent) if
    python-chi or credentials are not available.
    """
    import os
    try:
        from advisor.availability.blazar import BlazarBackend
    except Exception as exc:
        return {"available": False, "error": f"python-chi not installed: {exc}"}

    try:
        b = BlazarBackend()
        devs = b.list_devices()
        free = [d for d in devs if d.free_now]
        target_free = [d for d in free if d.machine_type == machine_type]
        target_all  = [d for d in devs if d.machine_type == machine_type]
        return {
            "available": True,
            "site": b.site_name,
            "auth_type": os.environ.get("OS_AUTH_TYPE", "unknown"),
            "total_devices": len(devs),
            "free_now": len(free),
            "target_machine_type": machine_type,
            "target_total": len(target_all),
            "target_free": len(target_free),
            "free_sample": [
                {"name": d.device_uid, "profiles": d.peripherals}
                for d in target_free[:5]
            ],
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _fmt_blazar(res: Dict[str, Any]) -> str:
    L: List[str] = []
    L.append("=" * 70)
    L.append("  LIVE STATE  (Blazar via python-chi)")
    L.append("=" * 70)
    if not res.get("available"):
        L.append(f"  status : UNAVAILABLE")
        L.append(f"  reason : {res.get('error', 'unknown')}")
        L.append("  => Source Chameleon Application Credentials and retry.")
    else:
        L.append(f"  site              : {res['site']}")
        L.append(f"  auth_type         : {res['auth_type']}")
        L.append(f"  total devices     : {res['total_devices']}")
        L.append(f"  free now          : {res['free_now']}")
        L.append(f"  '{res['target_machine_type']}' total : {res['target_total']}")
        L.append(f"  '{res['target_machine_type']}' free  : {res['target_free']}")
        if res["free_sample"]:
            L.append("  free sample       :")
            for d in res["free_sample"]:
                profiles = ", ".join(d["profiles"]) if d["profiles"] else "—"
                L.append(f"    {d['name']:<30} profiles: {profiles}")
    L.append("=" * 70)
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--machine-type", default="raspberrypi4-64")
    ap.add_argument("--json", action="store_true", help="emit raw JSON only")
    ap.add_argument("--no-blazar", action="store_true", help="skip Blazar live probe")
    args = ap.parse_args(argv)

    logger = RunLogger()
    res = run_probe(args.machine_type)

    blazar_res: Dict[str, Any] = {}
    if not args.no_blazar:
        blazar_res = probe_blazar(args.machine_type)
    res["blazar"] = blazar_res

    logger.log("probe", **res)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(_fmt(res))
        if not args.no_blazar:
            print()
            print(_fmt_blazar(blazar_res))
        print(f"\n[logged run_id={logger.run_id} -> {logger.log_path}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
