#!/usr/bin/env python3
"""Live Chameleon availability with reservation windows, per node, per site.

  python probe_availability.py --rc "~/Downloads/app-cred-*-openrc.sh"
  python probe_availability.py --rc "..." --nodes            # per-node detail
  python probe_availability.py --rc "..." --xlsx live.xlsx   # advisor export
  python probe_availability.py --rc "..." --json
  python probe_availability.py --reference                   # static API check

- Live state is in Blazar (one per site); the portal Host Calendar is a Blazar view.
- Chain: Keystone /auth/tokens -> catalog -> blazar -> {resource} + /allocations.
- Resource is os-hosts everywhere except CHI@Edge, which uses devices.
- Type field is node_type on hosts, machine_name on devices.
- Three states: down (reservable=False), busy (a window covers now), else free.
- free  -> available_hours until the next reservation starts (None = unbounded).
  busy  -> next_free at the end of the contiguous booked block, not just the
           current reservation: back-to-back leases are chained.
- Terminal rounds to hours and caps at >7d. The XLSX/JSON carry exact UTC
  timestamps, which is what the advisor needs to schedule a future booking.
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
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, __file__.rsplit("/", 1)[0])

TIMEOUT = 30
HORIZON = timedelta(days=7)          # beyond this we just say ">7d"
CONTIGUOUS_GAP = timedelta(minutes=30)   # gap below this counts as back-to-back
RESOURCES = (("os-hosts", "node_type"), ("devices", "machine_name"))


def _now():
    return datetime.now(timezone.utc)


def _dt(s):
    """Blazar emits naive UTC like 2026-08-06T15:00:00.000000."""
    try:
        v = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v


def human(delta):
    """Hours-precise, capped at the horizon. None means unbounded."""
    if delta is None or delta >= HORIZON:
        return ">7d"
    h = int(delta.total_seconds() // 3600)
    if h < 1:
        return f"{int(delta.total_seconds() // 60)}m"
    return f"{h}h" if h < 48 else f"{h // 24}d {h % 24}h"


def windows(reservations, now):
    """(busy_now, free_until, next_free, lease_id).

    free_until  when a currently-free node gets taken (None = nothing booked).
    next_free   when a currently-busy node frees, chaining back-to-back leases,
                because the first lease ending is not when you can actually get
                the node if another starts straight after.
    """
    spans = sorted(
        ((_dt(r.get("start_date")), _dt(r.get("end_date")), r.get("lease_id"))
         for r in reservations or []),
        key=lambda s: (s[0] or now))
    spans = [s for s in spans if s[0] and s[1]]

    current = next((s for s in spans if s[0] <= now < s[1]), None)
    if current is None:
        nxt = next((s[0] for s in spans if s[0] > now), None)
        return False, nxt, None, None

    cursor, lease = current[1], current[2]
    for start, end, _lid in spans:
        if start <= cursor + CONTIGUOUS_GAP and end > cursor:
            cursor = end
    return True, None, cursor, lease


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


def probe_site(env, rc_file=None):
    label = env.get("OS_REGION_NAME") or os.path.basename(rc_file or "?")
    out = {"site": label, "blazar": None, "kind": None, "nodes": [], "error": None}

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
        if not err:
            items = data.get(path.replace("os-", "")) or data.get("hosts") or []
            out["kind"] = path
            break
    else:
        out["error"] = "no usable resource endpoint"
        return out

    allocs, err = _get(f"{out['blazar']}/{out['kind']}/allocations", token)
    if err:
        out["error"] = f"allocations: {err}"
        return out
    by_id = {str(a.get("resource_id")): a.get("reservations") or []
             for a in allocs.get("allocations", [])}

    now = _now()
    for it in items:
        rid = str(it.get("id", ""))
        # KVM@TACC has no node_type; its hosts are typed by hypervisor.
        ntype = it.get(type_field) or it.get("hypervisor_type") or "unknown"
        reservable = it.get("reservable", True)
        busy, free_until, next_free, lease = windows(by_id.get(rid, []), now)

        if not reservable:
            status = "down"
        elif busy:
            status = "busy"
        else:
            status = "free"

        out["nodes"].append({
            "site": label, "node_type": ntype, "uid": it.get("uid") or rid,
            "name": (it.get("node_name") or it.get("name")
                     or it.get("hypervisor_hostname") or rid),
            "status": status, "reservable": bool(reservable),
            "immediately_available": status == "free",
            "free_until_utc": free_until.isoformat() if free_until else None,
            "available_hours": (round((free_until - now).total_seconds() / 3600, 2)
                                if free_until else None),
            "next_free_utc": next_free.isoformat() if next_free else None,
            "busy_hours_remaining": (round((next_free - now).total_seconds() / 3600, 2)
                                     if next_free else None),
            "lease_id": lease,
            "gpu_model": it.get("gpu.gpu_model"), "gpu_count": it.get("gpu.gpu_count"),
            "vcpus": it.get("vcpus"), "ram_gb": (
                round(int(it["memory_mb"]) / 1024) if str(it.get("memory_mb", "")).isdigit()
                else None),
        })
    return out


def by_type(nodes):
    """Aggregate per node_type.

    longest_hours is the best window you could get by picking the best free
    node; None means at least one free node has nothing booked after it, so the
    window is open-ended. shortest_hours is the same set's worst case, which is
    what warns you that "free" does not mean "free for long".
    """
    groups = defaultdict(list)
    for n in nodes:
        groups[n["node_type"]].append(n)

    agg = {}
    for t, ns in sorted(groups.items()):
        free = [n for n in ns if n["status"] == "free"]
        hours = [n["available_hours"] for n in free]
        finite = [h for h in hours if h is not None]
        busy = [n["busy_hours_remaining"] for n in ns
                if n["status"] == "busy" and n["busy_hours_remaining"] is not None]
        agg[t] = {
            "free": len(free),
            "busy": sum(n["status"] == "busy" for n in ns),
            "down": sum(n["status"] == "down" for n in ns),
            "total": len(ns),
            # any unbounded free node -> best case is open-ended
            "longest_hours": None if (free and len(finite) < len(hours))
                             else (max(finite) if finite else None),
            "shortest_hours": min(finite) if finite else None,
            "soonest_free_hours": min(busy) if busy else None,
        }
    return agg


def _hrs(h):
    return human(None if h is None else timedelta(hours=h))


def render(sites, show_nodes):
    print(f"Chameleon live availability  {_now().isoformat(timespec='seconds')}")
    live = [s for s in sites if s["error"] is None]
    for s in sorted(sites, key=lambda x: x["site"]):
        print(f"\n{s['site']}")
        if s["error"]:
            print(f"  NO DATA: {s['error']}")
            continue
        n = s["nodes"]
        f = sum(x["status"] == "free" for x in n)
        d = sum(x["status"] == "down" for x in n)
        print(f"  {s['blazar']} ({s['kind']})")
        print(f"  {f} free / {len(n)} total" + (f", {d} down" if d else ""))
        print(f"    {'node_type':30} {'free/total':>11}  {'now?':4} {'window':>16}")
        for t, a in by_type(n).items():
            if a["free"]:
                now_s, win = "YES", f"up to {_hrs(a['longest_hours'])}"
                # Warn when the shortest free window is materially worse than
                # the best: "3 free" can still mean "2 of them expire tonight".
                s = a["shortest_hours"]
                if s is not None and _hrs(s) != _hrs(a["longest_hours"]):
                    win += f" (min {_hrs(s)})"
            elif a["down"] == a["total"]:
                now_s, win = "DOWN", "unreservable"
            elif a["soonest_free_hours"] is not None:
                now_s, win = "no", f"free in {_hrs(a['soonest_free_hours'])}"
            else:
                now_s, win = "no", "unknown"
            cnt = f"{a['free']}/{a['total']}" + (f" ({a['down']}d)" if a["down"] else "")
            print(f"    {t:30} {cnt:>11}  {now_s:4} {win:>16}")
        if show_nodes:
            print()
            for x in sorted(n, key=lambda x: (x["node_type"], x["name"])):
                w = (f"free {_hrs(x['available_hours'])}" if x["status"] == "free"
                     else f"busy, free in {_hrs(x['busy_hours_remaining'])}"
                     if x["status"] == "busy" else "DOWN")
                print(f"      {x['node_type']:26} {str(x['name'])[:26]:26} {w}")
    if live:
        alln = [x for s in live for x in s["nodes"]]
        print(f"\nTOTAL {sum(x['status'] == 'free' for x in alln)} free / {len(alln)} "
              f"nodes across {len(live)} sites, "
              f"{sum(x['status'] == 'down' for x in alln)} down")


def to_xlsx(sites, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    hf, hfill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E79")
    fill = {"free": "C6EFCE", "busy": "FFEB9C", "down": "F8CBAD"}

    def sheet(ws, cols, rows, widths=None):
        ws.append(cols)
        for c in range(1, len(cols) + 1):
            ws.cell(row=1, column=c).font = hf
            ws.cell(row=1, column=c).fill = hfill
        for r in rows:
            ws.append([r.get(c) for c in cols])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, c in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(i)].width = \
                (widths or {}).get(c, min(max(12, len(c) + 2), 34))

    nodes = [n for s in sites if s["error"] is None for n in s["nodes"]]
    cols = ["site", "node_type", "name", "uid", "status", "reservable",
            "immediately_available", "available_hours", "free_until_utc",
            "busy_hours_remaining", "next_free_utc", "lease_id",
            "gpu_model", "gpu_count", "vcpus", "ram_gb"]
    ws = wb.active
    ws.title = "Nodes"
    sheet(ws, cols, nodes, {"name": 28, "uid": 38, "lease_id": 38,
                            "free_until_utc": 26, "next_free_utc": 26})
    for i, n in enumerate(nodes, start=2):
        ws.cell(row=i, column=5).fill = PatternFill(
            "solid", fgColor=fill.get(n["status"], "F2F2F2"))

    agg = []
    for s in sites:
        if s["error"]:
            continue
        for t, a in by_type(s["nodes"]).items():
            agg.append({"site": s["site"], "node_type": t, **a,
                        "longest_window": _hrs(a["longest_hours"]) if a["free"] else "",
                        "shortest_window": _hrs(a["shortest_hours"])
                        if a["shortest_hours"] is not None else "",
                        "soonest_free": _hrs(a["soonest_free_hours"])
                        if a["soonest_free_hours"] is not None else ""})
    sheet(wb.create_sheet("By node_type"),
          ["site", "node_type", "free", "busy", "down", "total",
           "longest_window", "longest_hours", "shortest_window", "shortest_hours",
           "soonest_free", "soonest_free_hours"],
          agg)

    sheet(wb.create_sheet("Sites"),
          ["site", "blazar", "kind", "free", "busy", "down", "total", "error"],
          [{"site": s["site"], "blazar": s["blazar"], "kind": s["kind"],
            "free": sum(x["status"] == "free" for x in s["nodes"]),
            "busy": sum(x["status"] == "busy" for x in s["nodes"]),
            "down": sum(x["status"] == "down" for x in s["nodes"]),
            "total": len(s["nodes"]), "error": s["error"]} for s in sites],
          {"blazar": 46, "error": 40})

    wb.save(path)
    print(f"\n[written] {path}  ({len(nodes)} nodes, exact UTC timestamps)")


def reference_check():
    """Does the public reference API expose live state? Settled: it does not."""
    from advisor.availability.reference_api import ReferenceApiBackend
    from advisor.config import settings
    base, site = settings.reference_api_base.rstrip("/"), settings.edge_site_uid
    b = ReferenceApiBackend(base=base, site=site)
    live = b.probe_live_status()
    return {"base": base, "edge_devices_exposed": len(b.list_devices()),
            "live_endpoint": live["live_endpoint"],
            "verdict": "LIVE-AWARE" if live["live_endpoint"] else "STATIC-ONLY"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rc", help="glob of openrc files, one per site")
    ap.add_argument("--nodes", action="store_true", help="per-node detail")
    ap.add_argument("--xlsx", help="write the advisor export to this path")
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
        print(json.dumps({"generated_utc": _now().isoformat(),
                          "reference": ref, "sites": sites}, indent=2))
    else:
        if ref:
            print(f"reference API {ref['base']}: {ref['verdict']}, "
                  f"{ref['edge_devices_exposed']} edge devices, "
                  f"live endpoint {ref['live_endpoint']}\n")
        if sites:
            render(sites, args.nodes)
    if args.xlsx and sites:
        to_xlsx(sites, args.xlsx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
