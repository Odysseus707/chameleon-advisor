"""probe_all_sites_availability: live free/reserved host state, all Chameleon sites.

Companion to probe_availability.py, which answers "can the public reference API
tell us live state" (it cannot, and its deeper endpoints are currently 500/502
anyway). This one goes to the authoritative source instead.

Live reservation state lives in Blazar, one Blazar per site. The portal Host
Calendar is a Blazar view. So:

    Keystone v3  ->  token + service catalog  ->  Blazar endpoint
    GET /os-hosts                             ->  every host and its node_type
    GET /leases                               ->  what is currently reserved

Blazar's os-hosts carries no "free" boolean, so free is derived as hosts minus
hosts covered by an active lease's reservations, the same derivation the Host
Calendar performs.

Direct REST rather than python-chi on purpose: python-chi's own site discovery
is failing right now ("Failed to fetch list of available Chameleon sites"), and
REST keeps the credential path explicit and replicable.

Credentials, either form, standard OpenStack env vars:

  application credential (recommended; what the Chameleon portal hands out)
    OS_AUTH_TYPE=v3applicationcredential
    OS_APPLICATION_CREDENTIAL_ID=...
    OS_APPLICATION_CREDENTIAL_SECRET=...

  password
    OS_USERNAME=... OS_PASSWORD=... OS_PROJECT_NAME=... OS_USER_DOMAIN_NAME=default

A Chameleon application credential is scoped to ONE site, so a true all-sites
sweep needs one per site. Per-site overrides are read first, as
OS_APPLICATION_CREDENTIAL_ID_UC / _TACC / _KVM / _EDGE (and _SECRET_<SUFFIX>).

  python probe_all_sites_availability.py
  python probe_all_sites_availability.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("needs requests: pip install requests")

SITES = [
    ("CHI@UC",   "uc",   "https://chi.uc.chameleoncloud.org:5000/v3"),
    ("CHI@TACC", "tacc", "https://chi.tacc.chameleoncloud.org:5000/v3"),
    ("KVM@TACC", "kvm",  "https://kvm.tacc.chameleoncloud.org:5000/v3"),
    ("CHI@Edge", "edge", "https://chi.edge.chameleoncloud.org:5000/v3"),
]
TIMEOUT = 30


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def env_for(suffix: str, name: str) -> str | None:
    """Per-site override first (OS_X_UC), then the plain variable (OS_X)."""
    return os.environ.get(f"{name}_{suffix.upper()}") or os.environ.get(name)


def auth_payload(suffix: str) -> tuple[dict | None, str]:
    """(Keystone v3 auth body, description) or (None, reason)."""
    ac_id = env_for(suffix, "OS_APPLICATION_CREDENTIAL_ID")
    ac_secret = env_for(suffix, "OS_APPLICATION_CREDENTIAL_SECRET")
    if ac_id and ac_secret:
        return ({"auth": {"identity": {
            "methods": ["application_credential"],
            "application_credential": {"id": ac_id, "secret": ac_secret}}}},
            "application_credential")

    user = env_for(suffix, "OS_USERNAME")
    pw = env_for(suffix, "OS_PASSWORD")
    project = env_for(suffix, "OS_PROJECT_NAME")
    if user and pw and project:
        domain = env_for(suffix, "OS_USER_DOMAIN_NAME") or "default"
        pdomain = env_for(suffix, "OS_PROJECT_DOMAIN_NAME") or domain
        return ({"auth": {
            "identity": {"methods": ["password"], "password": {"user": {
                "name": user, "password": pw, "domain": {"name": domain}}}},
            "scope": {"project": {"name": project,
                                  "domain": {"name": pdomain}}}}},
            "password")
    return None, "no credentials in environment"


def authenticate(auth_url: str, body: dict) -> tuple[str | None, list, str | None]:
    """(token, service catalog, error)."""
    try:
        r = requests.post(f"{auth_url}/auth/tokens", json=body, timeout=TIMEOUT)
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


def blazar_url(catalog: list) -> str | None:
    for svc in catalog:
        if svc.get("type") == "reservation" or svc.get("name") == "blazar":
            for ep in svc.get("endpoints", []):
                if ep.get("interface") == "public":
                    return ep["url"].rstrip("/")
    return None


def get(url: str, token: str) -> tuple[dict | None, str | None]:
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


def reachability(auth_url: str) -> str:
    """Endpoint liveness without credentials: a 200 means Keystone is up."""
    try:
        return f"reachable (HTTP {requests.get(auth_url, timeout=TIMEOUT).status_code})"
    except requests.RequestException as e:
        return f"unreachable ({type(e).__name__})"


def probe_site(name: str, suffix: str, auth_url: str) -> dict:
    out = {"site": name, "auth_url": auth_url, "checked_utc": now(),
           "auth": None, "blazar_endpoint": None, "hosts_total": None,
           "hosts_free": None, "by_node_type": {}, "leases_active": None,
           "error": None, "reachability": None}

    body, how = auth_payload(suffix)
    if body is None:
        out["error"] = how
        out["reachability"] = reachability(auth_url)
        return out
    out["auth"] = how

    token, catalog, err = authenticate(auth_url, body)
    if err:
        out["error"] = f"keystone auth failed: {err}"
        out["reachability"] = reachability(auth_url)
        return out

    bz = blazar_url(catalog)
    if not bz:
        out["error"] = "no reservation (blazar) endpoint in the service catalog"
        return out
    out["blazar_endpoint"] = bz

    hosts, err = get(f"{bz}/os-hosts", token)
    if err:
        out["error"] = f"blazar os-hosts: {err}"
        return out
    host_list = hosts.get("hosts", []) if isinstance(hosts, dict) else []
    out["hosts_total"] = len(host_list)

    # node_type is the field the advisor recommends on; degrade gracefully.
    by_type: dict[str, dict] = defaultdict(lambda: {"total": 0, "free": 0})
    host_type: dict[str, str] = {}
    for h in host_list:
        t = (h.get("node_type") or h.get("hypervisor_type")
             or h.get("device_type") or "unknown")
        hid = str(h.get("id") or h.get("hypervisor_hostname") or "")
        host_type[hid] = t
        by_type[t]["total"] += 1

    leases, err = get(f"{bz}/leases", token)
    reserved: set[str] = set()
    if err:
        out["error"] = f"blazar leases: {err} (host totals still valid)"
    else:
        llist = leases.get("leases", []) if isinstance(leases, dict) else []
        active = 0
        for lease in llist:
            if str(lease.get("status", "")).upper() not in ("ACTIVE", "STARTING"):
                continue
            active += 1
            for res in lease.get("reservations", []) or []:
                for alloc in res.get("host_ids", []) or []:
                    reserved.add(str(alloc))
        out["leases_active"] = active

    for hid, t in host_type.items():
        if hid not in reserved:
            by_type[t]["free"] += 1
    out["hosts_free"] = out["hosts_total"] - len(reserved & set(host_type))
    out["by_node_type"] = {k: dict(v) for k, v in sorted(by_type.items())}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    results = [probe_site(n, s, u) for n, s, u in SITES]

    print("=" * 74)
    print("  Chameleon live availability, all sites (Blazar via Keystone)")
    print(f"  {now()}")
    print("=" * 74)
    any_live = False
    for r in results:
        print(f"\n  {r['site']}")
        print(f"    keystone   : {r['auth_url']}")
        if r["error"]:
            print("    STATUS     : NO LIVE DATA")
            print(f"    reason     : {r['error']}")
            if r["reachability"]:
                print(f"    endpoint   : {r['reachability']}")
            continue
        any_live = True
        print(f"    auth       : {r['auth']}")
        print(f"    blazar     : {r['blazar_endpoint']}")
        print(f"    hosts      : {r['hosts_free']} free / {r['hosts_total']} total"
              f"   (active leases: {r['leases_active']})")
        if r["by_node_type"]:
            print(f"    {'node_type':32} {'free':>6} {'total':>6}")
            for t, v in r["by_node_type"].items():
                print(f"      {t:30} {v['free']:>6} {v['total']:>6}")

    print("\n" + "=" * 74)
    if not any_live:
        print("  NO SITE RETURNED LIVE STATE.")
        print("  Blazar is reachable but requires credentials. Set application")
        print("  credential env vars (see the module docstring) and re-run. A")
        print("  Chameleon application credential is scoped to ONE site, so a")
        print("  full sweep needs one per site via the _UC/_TACC/_KVM/_EDGE")
        print("  suffixed variables.")
    print("=" * 74)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"[written] {args.json_out}")
    return 0 if any_live else 2


if __name__ == "__main__":
    raise SystemExit(main())
