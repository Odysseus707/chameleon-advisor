#!/usr/bin/env python3
"""Live Chameleon availability: free vs reserved hosts per node_type, per site.

  python probe_availability.py --rc "~/Downloads/app-cred-*-openrc.sh"
  python probe_availability.py --rc "..." --json
  python probe_availability.py --reference        # static reference-API check

- Live state is in Blazar (one per site); the portal Host Calendar is a Blazar view.
- Chain: Keystone /auth/tokens -> catalog -> blazar -> {resource} + /allocations.
- Resource is os-hosts everywhere except CHI@Edge, which uses devices.
- Type field is node_type on hosts, machine_name on devices.
- free is derived, not read: a host is busy only if an allocation window covers now.
  Leases alone are useless here; a lease never names its hosts.
- An app credential is scoped to ONE site, so pass one openrc per site.
- --rc sources each openrc in a subshell, stdin closed. Secrets are never printed.
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

import requests

sys.path.insert(0, __file__.rsplit("/", 1)[0])

TIMEOUT = 30
# (resource path, field holding the machine type)
RESOURCES = (("os-hosts", "node_type"), ("devices", "machine_name"))


def _now():
    return datetime.now(timezone.utc)


def load_rc(path):
    """Source an openrc in a subshell; return its OS_* vars. stdin closed so a
    password-prompting openrc fails fast instead of hanging."""
    p = subprocess.run(["bash", "-c", f'set -a; . "{path}" >/dev/null 2>&1; set +a; env'],
                       capture_output=True, text=True, timeout=30,
                       stdin=subprocess.DEVNULL)
    return {k: v for k, v in (l.partition("=")[::2] for l in p.stdout.splitlines())
            if k.startswith("OS_") and v}


def _auth_body(env):
    if env.get("OS_APPLICATION_CREDENTIAL_ID"):
        return {"auth": {"identity": {"methods": ["application_credential"],
                "application_credential": {
                    "id": env["OS_APPLICATION_CREDENTIAL_ID"],
                    "secret": env.get("OS_APPLICATION_CREDENTIAL_SECRET", "")}}}}
    if env.get("OS_USERNAME") and env.get("OS_PASSWORD"):
        d = env.get("OS_USER_DOMAIN_NAME", "default")
        return {"auth": {
            "identity": {"methods": ["password"], "password": {"user": {
                "name": env["OS_USERNAME"], "password": env["OS_PASSWORD"],
                "domain": {"name": d}}}},
            "scope": {"project": {"name": env.get("OS_PROJECT_NAME", ""),
                                  "domain": {"name": d}}}}}
    return None


def _get(url, token):
    try:
        r = requests.get(url, headers={"X-Auth-Token": token}, timeout=TIMEOUT)
    except requests.RequestException as e:
        return None, type(e).__name__
    return (r.json(), None) if r.status_code == 200 else (None, f"HTTP {r.status_code}")


def _busy_now(res, now):
    """A reservation makes its host busy only if its window covers this moment."""
    def dt(s):
        try:
            v = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
    start, end = dt(res.get("start_date")), dt(res.get("end_date"))
    return not ((start and start > now) or (end and end < now))


def probe_site(env, rc_file=None):
    label = env.get("OS_REGION_NAME") or os.path.basename(rc_file or "?")
    out = {"site": label, "blazar": None, "kind": None, "total": None,
           "free": None, "by_type": {}, "error": None}

    body = _auth_body(env)
    if not body or not env.get("OS_AUTH_URL"):
        out["error"] = "no credentials or OS_AUTH_URL in this RC"
        return out

    url = env["OS_AUTH_URL"].rstrip("/")
    url = url if url.endswith("/v3") else url + "/v3"
    try:
        r = requests.post(f"{url}/auth/tokens", json=body, timeout=TIMEOUT)
    except requests.RequestException as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    if r.status_code not in (200, 201):
        out["error"] = f"keystone HTTP {r.status_code}"
        return out
    token = r.headers.get("X-Subject-Token")

    for svc in r.json().get("token", {}).get("catalog", []):
        if svc.get("type") == "reservation":
            for ep in svc.get("endpoints", []):
                if ep.get("interface") == "public":
                    out["blazar"] = ep["url"].rstrip("/")
    if not out["blazar"]:
        out["error"] = "no reservation endpoint in catalog"
        return out

    for path, type_field in RESOURCES:
        data, err = _get(f"{out['blazar']}/{path}", token)
        if err:
            continue
        items = data.get(path.replace("os-", "")) or data.get("hosts") or []
        out["kind"] = path
        break
    else:
        out["error"] = f"no usable resource endpoint ({', '.join(p for p, _ in RESOURCES)})"
        return out

    out["total"] = len(items)
    by_type = defaultdict(lambda: {"total": 0, "free": 0})
    kind_of = {}
    for it in items:
        # KVM@TACC has no node_type; its hosts are typed by hypervisor.
        t = it.get(type_field) or it.get("hypervisor_type") or "unknown"
        kind_of[str(it.get("id", ""))] = t
        by_type[t]["total"] += 1

    allocs, err = _get(f"{out['blazar']}/{out['kind']}/allocations", token)
    if err:
        out["error"] = f"allocations: {err}; free not computed"
        return out
    now = _now()
    busy = {str(a.get("resource_id")) for a in allocs.get("allocations", [])
            if any(_busy_now(x, now) for x in a.get("reservations") or [])}

    for hid, t in kind_of.items():
        if hid not in busy:
            by_type[t]["free"] += 1
    out["free"] = out["total"] - len(busy & set(kind_of))
    out["by_type"] = {k: dict(v) for k, v in sorted(by_type.items())}
    return out


def reference_check():
    """Does the public reference API expose live state? Settled: it does not."""
    from advisor.availability.reference_api import ReferenceApiBackend
    from advisor.config import settings
    base, site = settings.reference_api_base.rstrip("/"), settings.edge_site_uid
    b = ReferenceApiBackend(base=base, site=site)
    live = b.probe_live_status()
    devices = b.list_devices()
    return {"base": base, "edge_devices_exposed": len(devices),
            "live_endpoint": live["live_endpoint"],
            "verdict": "LIVE-AWARE" if live["live_endpoint"] else "STATIC-ONLY"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rc", help='glob of openrc files, one per site')
    ap.add_argument("--reference", action="store_true",
                    help="also run the static reference-API check")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ref = reference_check() if args.reference else None
    sites = []
    if args.rc:
        for p in sorted(glob.glob(os.path.expanduser(args.rc))):
            sites.append(probe_site(load_rc(p), p))
    elif not args.reference:
        ap.error("--rc is required for live state (or use --reference)")

    if args.json:
        print(json.dumps({"reference": ref, "sites": sites}, indent=2))
        return 0

    if ref:
        print(f"reference API {ref['base']}: {ref['verdict']}, "
              f"{ref['edge_devices_exposed']} edge devices exposed, "
              f"live endpoint {ref['live_endpoint']}\n")

    print(f"Chameleon live availability  {_now().isoformat(timespec='seconds')}")
    live = [s for s in sites if s["total"] is not None]
    for s in sorted(sites, key=lambda x: x["site"]):
        print(f"\n{s['site']}")
        if s["total"] is None:
            print(f"  NO DATA: {s['error']}")
            continue
        print(f"  {s['blazar']} ({s['kind']})")
        print(f"  {s['free']} free / {s['total']} total")
        if s["error"]:
            print(f"  note: {s['error']}")
        for t, v in s["by_type"].items():
            print(f"    {t:32} {v['free']:>5} / {v['total']:>5}")
    if live:
        print(f"\nTOTAL {sum(s['free'] for s in live)} free / "
              f"{sum(s['total'] for s in live)} hosts across {len(live)} sites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
