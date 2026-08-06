"""BlazarRestBackend: live reservation state from Blazar over plain REST.

Why this exists alongside blazar.py. That backend goes through python-chi,
which needs its own site-discovery call that is currently failing, and it only
ever sees one site. This talks to Keystone and Blazar directly:

    Keystone /auth/tokens -> catalog -> blazar -> {resource} + /allocations

and it answers the question the advisor actually asks: not just "is this device
free" but "free for how long", and if not, "when does it free up".

Three states, because reservable=False is neither free nor reserved. A host in
maintenance is unbookable, and reporting it free is exactly the failure that
hands a user a spec that cannot be submitted. 111 of 655 nodes were in that
state when this was written.

Resource paths differ by site: os-hosts everywhere, devices on CHI@Edge, whose
machine type lives in machine_name (device_type is uniformly "container").

Credentials: one Chameleon application credential per site, as openrc files.
Point CHAMELEON_RC_GLOB at them. Each is sourced in a subshell with stdin
closed, so a password-prompting openrc fails fast rather than hanging, and only
OS_* variables cross back. Secrets are never logged.
"""
from __future__ import annotations

import glob
import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..config import settings
from .base import AvailabilityBackend, DeviceAvailability

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

TIMEOUT = 30
CONTIGUOUS_GAP = timedelta(minutes=30)
RESOURCES = (("os-hosts", "node_type"), ("devices", "machine_name"))

_ARM_HINTS = ("arm", "raspberry", "jetson", "xavier", "orin", "thunder")
_GPU_HINTS = ("gpu", "jetson", "nvidia")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(s):
    """Blazar emits naive UTC like 2026-08-06T15:00:00.000000."""
    try:
        v = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v


def windows(reservations, now):
    """(busy_now, free_until, next_free, lease_id).

    next_free chains back-to-back leases: the current lease ending is not when
    you can get the node if another starts thirty minutes later.
    """
    spans = sorted(
        ((_dt(r.get("start_date")), _dt(r.get("end_date")), r.get("lease_id"))
         for r in reservations or []),
        key=lambda s: (s[0] or now))
    spans = [s for s in spans if s[0] and s[1]]

    current = next((s for s in spans if s[0] <= now < s[1]), None)
    if current is None:
        return False, next((s[0] for s in spans if s[0] > now), None), None, None

    cursor, lease = current[1], current[2]
    for start, end, _lid in spans:
        if start <= cursor + CONTIGUOUS_GAP and end > cursor:
            cursor = end
    return True, None, cursor, lease


def load_rc(path: str) -> Dict[str, str]:
    """Source an openrc in a subshell; return its OS_* vars only."""
    p = subprocess.run(
        ["bash", "-c", f'set -a; . "{path}" >/dev/null 2>&1; set +a; env'],
        capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    return {k: v for k, v in (l.partition("=")[::2] for l in p.stdout.splitlines())
            if k.startswith("OS_") and v}


def _auth_body(env: Dict[str, str]) -> Optional[dict]:
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


def probe_site(env: Dict[str, str], rc_file: Optional[str] = None) -> dict:
    """Raw per-site result: {site, blazar, kind, nodes[], error}."""
    label = env.get("OS_REGION_NAME") or os.path.basename(rc_file or "?")
    out = {"site": label, "blazar": None, "kind": None, "nodes": [], "error": None}
    if requests is None:
        out["error"] = "requests not installed"
        return out

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
        reservable = bool(it.get("reservable", True))
        busy, free_until, next_free, lease = windows(by_id.get(rid, []), now)
        status = "down" if not reservable else ("busy" if busy else "free")
        out["nodes"].append({
            "site": label, "node_type": ntype, "uid": it.get("uid") or rid,
            "name": (it.get("node_name") or it.get("name")
                     or it.get("hypervisor_hostname") or rid),
            "status": status, "reservable": reservable,
            "immediately_available": status == "free",
            "free_until_utc": free_until.isoformat() if free_until else None,
            "available_hours": (round((free_until - now).total_seconds() / 3600, 2)
                                if free_until else None),
            "next_free_utc": next_free.isoformat() if next_free else None,
            "busy_hours_remaining": (round((next_free - now).total_seconds() / 3600, 2)
                                     if next_free else None),
            "lease_id": lease,
            "gpu_model": it.get("gpu.gpu_model"), "gpu_count": it.get("gpu.gpu_count"),
            "vcpus": it.get("vcpus"),
            "ram_gb": (round(int(it["memory_mb"]) / 1024)
                       if str(it.get("memory_mb", "")).isdigit() else None),
        })
    return out


def fetch_sites(rc_glob: Optional[str] = None) -> List[dict]:
    """Probe every site whose openrc matches the glob. Used by the CLI report."""
    pattern = rc_glob or settings.chameleon_rc_glob
    return [probe_site(load_rc(p), p)
            for p in sorted(glob.glob(os.path.expanduser(pattern or "")))]


def to_availability(n: dict) -> DeviceAvailability:
    low = n["node_type"].lower()
    return DeviceAvailability(
        device_uid=str(n["name"]),
        machine_type=n["node_type"],
        site=n["site"],
        architecture="arm64" if any(h in low for h in _ARM_HINTS) else "x86_64",
        gpu=any(h in low for h in _GPU_HINTS) or bool(n.get("gpu_count")),
        peripherals=[],
        # A down node is not free, and it is not merely reserved either. The
        # advisor must not offer it, so free_now is False and reservable says why.
        free_now=n["status"] == "free",
        reserved_until=n.get("next_free_utc"),
        next_free_window=(n.get("free_until_utc") if n["status"] == "free"
                          else n.get("next_free_utc")),
        reservable=n["reservable"],
        available_hours=n["available_hours"] if n["status"] == "free" else None,
        source="blazar",
        live_state_known=True,
    )


class BlazarBackend(AvailabilityBackend):
    """Live Blazar state, any site, no python-chi."""

    name = "blazar"
    reports_live_state = True

    def __init__(self, rc_glob: Optional[str] = None,
                 site: Optional[str] = None, all_sites: bool = False):
        if requests is None:
            raise RuntimeError(
                "BlazarBackend requires requests. `pip install requests`, "
                "or select AVAILABILITY_BACKEND=reference_api.")
        self.rc_glob = rc_glob or settings.chameleon_rc_glob
        if not self.rc_glob:
            raise RuntimeError(
                "BlazarBackend needs credentials. Set CHAMELEON_RC_GLOB to "
                "your Chameleon application-credential openrc files, e.g. "
                "'~/Downloads/app-cred-*-openrc.sh'. One per site, since a "
                "credential is scoped to a single site.")
        # Default to the configured site; the advisor is CHI@Edge-shaped today.
        self.site = None if all_sites else (site or settings.chi_site_name)
        self._cache: Optional[List[dict]] = None

    def _sites(self) -> List[dict]:
        if self._cache is None:
            self._cache = fetch_sites(self.rc_glob)
        return self._cache

    def _nodes(self) -> List[dict]:
        return [n for s in self._sites() if not s["error"] for n in s["nodes"]
                if self.site is None or n["site"] == self.site]

    def list_devices(self, machine_type: Optional[str] = None
                     ) -> List[DeviceAvailability]:
        return [to_availability(n) for n in self._nodes()
                if machine_type is None or n["node_type"] == machine_type]

    def get_device(self, device_uid: str) -> Optional[DeviceAvailability]:
        return next((to_availability(n) for n in self._nodes()
                     if str(n["name"]) == device_uid or str(n["uid"]) == device_uid),
                    None)

    def healthcheck(self) -> dict:
        sites = self._sites()
        ok = [s for s in sites if not s["error"]]
        nodes = self._nodes()
        return {
            "backend": self.name,
            "reachable": bool(ok),
            "sites_ok": [s["site"] for s in ok],
            "sites_failed": {s["site"]: s["error"] for s in sites if s["error"]},
            "scoped_to": self.site or "all sites",
            "devices": len(nodes),
            "free_now": sum(n["status"] == "free" for n in nodes),
            "down": sum(n["status"] == "down" for n in nodes),
        }
