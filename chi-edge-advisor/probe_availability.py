#!/usr/bin/env python3
"""probe_availability.py -- where does live Chameleon availability come from?

Two halves, because the answer took two measurements.

HALF 1, the original question and the FIRST deliverable. Does the Chameleon
*reference API* (https://api.chameleoncloud.org) reflect live CHI@Edge
reservation state, or only static hardware inventory?

  1. Reachability: is the reference API up and does the `edge` site exist?
  2. Inventory: walk /sites/edge -> clusters -> nodes. How many CHI@Edge
     devices does it actually expose?
  3. Target device: locate a specific edge device type in that inventory.
  4. Schema: inspect a node record for reservation/availability/lease/state
     fields, the fields required to express live state at all.
  5. Live endpoints: probe undocumented candidate live-status paths.
  6. Verdict: STATIC-ONLY vs LIVE-AWARE, with the evidence that decided it.

Measured answer: STATIC-ONLY, and it exposes no edge inventory whatsoever.
So live state has to come from somewhere else.

HALF 2, that somewhere else. Live reservation state lives in Blazar, one per
site; the portal Host Calendar is a Blazar view. Straight REST rather than
python-chi, because python-chi's own site discovery is currently failing:

    Keystone v3 /auth/tokens          ->  token + service catalog
    service catalog                   ->  the "reservation" (blazar) endpoint
    GET {blazar}/os-hosts             ->  every host and its node_type
    GET {blazar}/os-hosts/allocations ->  which hosts are reserved, and when

free is derived, not read: os-hosts carries no free boolean. A host counts as
busy only if an allocation's window contains the present moment, so a
reservation starting tomorrow does not make a host busy today. The allocations
endpoint is essential: a lease's own reservation payload does NOT name its
hosts, so reading leases alone reports every host free everywhere.

CREDENTIALS. A Chameleon application credential is scoped to ONE site, so a
real sweep needs one per site. Point --rc at the portal's openrc files and this
sources each in a subshell with stdin closed (a password-prompting openrc then
fails fast instead of hanging). Only OS_* variables come back; secrets are
never printed, logged, or written to --json output.

Run:
  python probe_availability.py                                  # reference-API probe
  python probe_availability.py --rc "~/Downloads/app-cred-*-openrc.sh"
  python probe_availability.py --rc "..." --no-reference --json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
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

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

RESERVATION_KEYS = ("reserv", "avail", "free", "status", "lease", "state", "booking")

# A baremetal site whose node schema we sample to characterize what the
# reference API models in general (the edge site itself exposes no nodes).
_SCHEMA_SAMPLE_SITE = "tacc"

TIMEOUT = 30

# Used only when --rc is absent and OS_* vars are exported by hand.
FALLBACK_SITES = [
    ("CHI@UC",   "https://chi.uc.chameleoncloud.org:5000/v3"),
    ("CHI@TACC", "https://chi.tacc.chameleoncloud.org:5000/v3"),
    ("KVM@TACC", "https://kvm.tacc.chameleoncloud.org:5000/v3"),
    ("CHI@Edge", "https://chi.edge.chameleoncloud.org:5000/v3"),
]


# =========================================================== HALF 1: reference API

def _sample_reference_node_schema(base: str) -> Dict[str, Any]:
    """Fetch one node from a baremetal site and inspect its schema shape."""
    out: Dict[str, Any] = {"keys": [], "reservation_like_keys": [], "sampled": None}
    clusters = get_json(f"{base}/sites/{_SCHEMA_SAMPLE_SITE}/clusters.json")
    if not clusters.ok or not clusters.json.get("items"):
        return out
    cuid = clusters.json["items"][0]["uid"]
    nodes = get_json(f"{base}/sites/{_SCHEMA_SAMPLE_SITE}/clusters/{cuid}/nodes.json")
    if not nodes.ok or not nodes.json.get("items"):
        return out
    nuid = nodes.json["items"][0]["uid"]
    node = get_json(
        f"{base}/sites/{_SCHEMA_SAMPLE_SITE}/clusters/{cuid}/nodes/{nuid}.json")
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
    result: Dict[str, Any] = {"base": base, "edge_site": site,
                              "machine_type": machine_type}

    # 1. Reachability -----------------------------------------------------
    site_res = get_json(f"{base}/sites/{site}.json")
    result["api_reachable"] = site_res.ok
    result["edge_site_exists"] = bool(
        site_res.ok and isinstance(site_res.json, dict)
        and site_res.json.get("uid") == site)

    # 2. Inventory: how many edge devices does the reference API expose? ---
    clusters = get_json(f"{base}/sites/{site}/clusters.json")
    result["edge_cluster_count"] = (
        clusters.json.get("total")
        if clusters.ok and isinstance(clusters.json, dict) else None)
    edge_devices = backend.list_devices() if result["edge_site_exists"] else []
    result["edge_device_count"] = len(edge_devices)
    result["edge_device_uids"] = [d.device_uid for d in edge_devices[:20]]

    # 3. Target device of the requested machine_type ----------------------
    result["target_devices_found"] = len(
        [d for d in edge_devices if d.machine_type == machine_type])

    # 4. Reference node schema: any reservation-like fields at all? --------
    result["node_schema"] = _sample_reference_node_schema(base)

    # 5. Live-status endpoint probe ---------------------------------------
    result["live_probe"] = backend.probe_live_status()

    # 6. Verdict ----------------------------------------------------------
    has_live_endpoint = result["live_probe"]["live_endpoint"] is not None
    schema_has_reservation = bool(result["node_schema"]["reservation_like_keys"])
    result["verdict"] = ("LIVE-AWARE" if has_live_endpoint or schema_has_reservation
                         else "STATIC-ONLY")
    result["reference_exposes_edge_inventory"] = result["edge_device_count"] > 0
    result["live_state_source_required"] = (
        "blazar" if result["verdict"] == "STATIC-ONLY" else "reference_api")
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
    L.append(f"     '{res['machine_type']}' devices in reference API : "
             f"{res['target_devices_found']}")
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
            L.append("  Moreover it exposes NO CHI@Edge device inventory at all "
                     "(edge site has 0 clusters / 0 nodes).")
        L.append("  Evidence:")
        L.append("    - no live-status endpoint responded")
        L.append("    - node records carry only static hardware fields")
        L.append("      (no reservation/availability/lease/state fields)")
        L.append("")
        L.append("  => Live availability MUST come from Blazar.")
        L.append('     Re-run with --rc "<glob of openrc files>" for live state.')
    else:
        L.append("  The reference API appears to expose live state; verify the")
        L.append("  discovered endpoint before trusting it as authoritative.")
    L.append("=" * 70)
    return "\n".join(L)


# ================================================= HALF 2: live Blazar, all sites

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _blank(label: str, rc: Optional[str], err: str) -> Dict[str, Any]:
    return {"site": label, "auth_url": None, "rc_file": rc, "checked_utc": _now(),
            "auth": None, "blazar_endpoint": None, "resource_kind": None,
            "hosts_total": None, "hosts_free": None, "by_node_type": {},
            "leases_active": None, "error": err}


def load_rc(path: str):
    """Source an openrc in a subshell and capture its OS_* variables.

    stdin is closed so a password-prompting openrc fails fast instead of
    hanging forever. Only OS_* names cross back, and none are ever printed.
    """
    script = f'set -a; . "{path}" >/dev/null 2>&1; set +a; env'
    try:
        proc = subprocess.run(["bash", "-c", script], capture_output=True,
                              text=True, timeout=30, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return {}, "sourcing timed out (interactive password prompt?)"
    if proc.returncode != 0:
        return {}, f"bash exited {proc.returncode}"
    env = {k: v for k, v in
           (line.partition("=")[::2] for line in proc.stdout.splitlines())
           if k.startswith("OS_") and v}
    return (env, None) if env else ({}, "no OS_* variables exported")


def auth_payload(env: Dict[str, str]):
    """(Keystone v3 auth body, description) or (None, reason)."""
    ac_id = env.get("OS_APPLICATION_CREDENTIAL_ID")
    ac_secret = env.get("OS_APPLICATION_CREDENTIAL_SECRET")
    if ac_id and ac_secret:
        return ({"auth": {"identity": {
            "methods": ["application_credential"],
            "application_credential": {"id": ac_id, "secret": ac_secret}}}},
            "application_credential")

    user, pw = env.get("OS_USERNAME"), env.get("OS_PASSWORD")
    project = env.get("OS_PROJECT_NAME")
    if user and pw and project:
        domain = env.get("OS_USER_DOMAIN_NAME") or "default"
        pdomain = env.get("OS_PROJECT_DOMAIN_NAME") or domain
        return ({"auth": {
            "identity": {"methods": ["password"], "password": {"user": {
                "name": user, "password": pw, "domain": {"name": domain}}}},
            "scope": {"project": {"name": project,
                                  "domain": {"name": pdomain}}}}},
            "password")
    return None, "no application credential or password in this environment"


def _parse_dt(s):
    """Blazar emits naive UTC like 2026-08-06T15:00:00.000000."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _covers_now(res: dict, now_dt) -> bool:
    """True if this reservation's window contains the present moment."""
    start, end = _parse_dt(res.get("start_date")), _parse_dt(res.get("end_date"))
    if start and start > now_dt:
        return False          # future reservation: the host is free right now
    if end and end < now_dt:
        return False          # already over
    return True


def _v3(url: str) -> str:
    url = url.rstrip("/")
    return url if url.endswith("/v3") else url + "/v3"


def _authenticate(auth_url: str, body: dict):
    try:
        r = requests.post(f"{_v3(auth_url)}/auth/tokens", json=body, timeout=TIMEOUT)
    except requests.RequestException as e:
        return None, [], f"{type(e).__name__}: {e}"
    if r.status_code not in (200, 201):
        try:
            detail = (r.json().get("error", {}) or {}).get("message", "")
        except ValueError:
            detail = r.text[:160]
        return None, [], f"HTTP {r.status_code}: {detail}"
    return (r.headers.get("X-Subject-Token"),
            (r.json().get("token", {}) or {}).get("catalog", []) or [], None)


def _blazar_url(catalog: list) -> Optional[str]:
    for svc in catalog:
        if svc.get("type") == "reservation" or svc.get("name") == "blazar":
            for ep in svc.get("endpoints", []):
                if ep.get("interface") == "public":
                    return ep["url"].rstrip("/")
    return None


def _get(url: str, token: str):
    try:
        r = requests.get(url, headers={"X-Auth-Token": token}, timeout=TIMEOUT)
    except requests.RequestException as e:
        return None, f"{type(e).__name__}: {e}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    try:
        return r.json(), None
    except ValueError:
        return None, "non-JSON response"


def probe_site(label: str, auth_url: str, env: Dict[str, str],
               rc_file: Optional[str]) -> Dict[str, Any]:
    out = _blank(label, rc_file, "")
    out["auth_url"], out["error"] = auth_url, None

    body, how = auth_payload(env)
    if body is None:
        out["error"] = how
        return out
    out["auth"] = how

    token, catalog, err = _authenticate(auth_url, body)
    if err:
        out["error"] = f"keystone auth failed: {err}"
        return out

    bz = _blazar_url(catalog)
    if not bz:
        types = sorted({s.get("type", "?") for s in catalog})
        out["error"] = ("no reservation (blazar) endpoint in the service "
                        f"catalog; services present: {', '.join(types)}")
        return out
    out["blazar_endpoint"] = bz

    # CHI@Edge reserves *devices*, not hosts, and 404s on os-hosts. Try both.
    resource = "os-hosts"
    hosts, err = _get(f"{bz}/os-hosts", token)
    if err and "404" in err:
        resource = "os-devices"
        hosts, err = _get(f"{bz}/os-devices", token)
    if err:
        out["error"] = f"blazar {resource}: {err}"
        return out
    out["resource_kind"] = resource
    host_list = (hosts.get("hosts") or hosts.get("devices") or []
                 if isinstance(hosts, dict) else [])
    out["hosts_total"] = len(host_list)

    by_type: Dict[str, dict] = defaultdict(lambda: {"total": 0, "free": 0})
    host_type: Dict[str, str] = {}
    for h in host_list:
        t = (h.get("node_type") or h.get("hypervisor_type")
             or h.get("device_type") or "unknown")
        hid = str(h.get("id") or h.get("hypervisor_hostname") or "")
        host_type[hid] = t
        by_type[t]["total"] += 1

    # Which hosts are reserved RIGHT NOW. A lease's reservation payload does
    # not name its hosts, so reading leases alone reports everything free. The
    # resource-to-reservation mapping lives on the allocations endpoint, which
    # is also what the portal Host Calendar reads.
    reserved: set = set()
    allocs, aerr = _get(f"{bz}/{resource}/allocations", token)
    if aerr:
        out["error"] = (f"blazar {resource}/allocations: {aerr}; free counts "
                        "could not be computed")
    else:
        now_dt = datetime.now(timezone.utc)
        alist = (allocs.get("allocations", []) if isinstance(allocs, dict)
                 else allocs if isinstance(allocs, list) else [])
        for a in alist:
            rid = str(a.get("resource_id") or "")
            if any(_covers_now(r, now_dt) for r in (a.get("reservations") or [])):
                reserved.add(rid)

    leases, lerr = _get(f"{bz}/leases", token)
    if not lerr:
        llist = leases.get("leases", []) if isinstance(leases, dict) else []
        out["leases_active"] = sum(
            1 for l in llist
            if str(l.get("status", "")).upper() in ("ACTIVE", "STARTING"))

    for hid, t in host_type.items():
        if hid not in reserved:
            by_type[t]["free"] += 1
    out["hosts_free"] = out["hosts_total"] - len(reserved & set(host_type))
    out["by_node_type"] = {k: dict(v) for k, v in sorted(by_type.items())}
    return out


def run_live(rc_glob: Optional[str]) -> List[Dict[str, Any]]:
    if requests is None:
        return [_blank("(all)", None, "needs requests: pip install requests")]
    results: List[Dict[str, Any]] = []
    if rc_glob:
        paths = sorted(glob.glob(os.path.expanduser(rc_glob)))
        if not paths:
            return [_blank("(all)", None, f"no RC files matched {rc_glob}")]
        for p in paths:
            env, err = load_rc(p)
            label = env.get("OS_REGION_NAME") or os.path.basename(p)
            if err:
                results.append(_blank(label, p, f"could not source RC: {err}"))
            elif not env.get("OS_AUTH_URL"):
                results.append(_blank(label, p, "RC defines no OS_AUTH_URL"))
            else:
                results.append(probe_site(label, env["OS_AUTH_URL"], env, p))
    else:
        env = {k: v for k, v in os.environ.items() if k.startswith("OS_")}
        for label, url in FALLBACK_SITES:
            results.append(probe_site(label, env.get("OS_AUTH_URL") or url,
                                      env, None))
    return results


def _fmt_live(results: List[Dict[str, Any]]) -> str:
    L: List[str] = []
    L.append("=" * 78)
    L.append("  LIVE STATE  (Blazar via Keystone, all sites)")
    L.append(f"  {_now()}")
    L.append("=" * 78)
    live = [r for r in results if r["hosts_total"] is not None]
    for r in sorted(results, key=lambda x: str(x["site"])):
        L.append(f"\n  {r['site']}")
        if r["auth_url"]:
            L.append(f"    keystone   : {r['auth_url']}")
        if r["hosts_total"] is None:
            L.append("    STATUS     : NO LIVE DATA")
            L.append(f"    reason     : {r['error']}")
            continue
        L.append(f"    blazar     : {r['blazar_endpoint']}  ({r['resource_kind']})")
        L.append(f"    hosts      : {r['hosts_free']} free / {r['hosts_total']} "
                 f"total   (active leases: {r['leases_active']})")
        if r["error"]:
            L.append(f"    note       : {r['error']}")
        if r["by_node_type"]:
            L.append(f"      {'node_type':34} {'free':>6} {'total':>6}")
            for t, v in r["by_node_type"].items():
                L.append(f"      {t:34} {v['free']:>6} {v['total']:>6}")
    if live:
        tf = sum(r["hosts_free"] or 0 for r in live)
        tt = sum(r["hosts_total"] or 0 for r in live)
        L.append("\n" + "-" * 78)
        L.append(f"  TOTAL across {len(live)} site(s) with live data: "
                 f"{tf} free / {tt} hosts")
    else:
        L.append("\n  No site returned live state. A Chameleon application")
        L.append("  credential is scoped to ONE site, so pass --rc with one")
        L.append("  openrc per site.")
    L.append("=" * 78)
    return "\n".join(L)


# =================================================================== entrypoint

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--machine-type", default="raspberrypi4-64")
    ap.add_argument("--json", action="store_true", help="emit raw JSON only")
    ap.add_argument("--rc", default=None,
                    help='glob of openrc files, e.g. '
                         '"~/Downloads/app-cred-*-openrc.sh"')
    ap.add_argument("--no-reference", action="store_true",
                    help="skip the reference-API probe (half 1)")
    ap.add_argument("--no-live", "--no-blazar", dest="no_live",
                    action="store_true",
                    help="skip the live Blazar sweep (half 2)")
    args = ap.parse_args(argv)

    logger = RunLogger()
    res: Dict[str, Any] = {}
    if not args.no_reference:
        res = run_probe(args.machine_type)
    live = [] if args.no_live else run_live(args.rc)
    res["live_sites"] = live

    logger.log("probe", **res)

    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if not args.no_reference:
            print(_fmt(res))
            print()
        if not args.no_live:
            print(_fmt_live(live))
        print(f"\n[logged run_id={logger.run_id} -> {logger.log_path}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
