"""BlazarBackend: live reservation state from Blazar over plain REST.

    Keystone /auth/tokens -> catalog -> blazar -> {resource} + /allocations

Replaced a python-chi implementation whose site discovery was failing and which
only ever saw one site. This answers the question the advisor actually asks:
not just "is this device free" but "free for how long", and if not, "when".

Blazar has NO server-side filter: GET /os-hosts?node_type=... returns every
host regardless. So narrowing has to happen by contacting fewer sites, which is
what `machine_types` plus the resource catalog do. 37 of 41 types live on a
single site, making a targeted fetch roughly 6x cheaper than the full sweep.

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
import logging
import os
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from ..config import settings
from .base import AvailabilityBackend, DeviceAvailability

log = logging.getLogger(__name__)

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


def keystone_auth(env: Dict[str, str]) -> tuple[Optional[str], Optional[dict], Optional[str]]:
    """Authenticate against Keystone: return (token, token_body, error).

    Exactly one of token / error is set. Split out of probe_site because the
    token body is worth more than the token: it also carries the service catalog
    and, on a scoped token, ``token["project"]`` - which is how a connected
    session learns its project name without a second round trip.

    This is the only POST in this module. Everything else here is GET.
    """
    if requests is None:
        return None, None, "requests not installed"

    body = _auth_body(env)
    if not body or not env.get("OS_AUTH_URL"):
        return None, None, "no credentials or OS_AUTH_URL in this RC"

    url = env["OS_AUTH_URL"].rstrip("/")
    url = url if url.endswith("/v3") else url + "/v3"
    try:
        r = requests.post(f"{url}/auth/tokens", json=body, timeout=TIMEOUT)
    except requests.RequestException as e:
        return None, None, f"{type(e).__name__}: {e}"
    if r.status_code not in (200, 201):
        return None, None, f"keystone HTTP {r.status_code}"
    return r.headers.get("X-Subject-Token"), r.json(), None


def public_endpoint(token_body: Optional[dict], service_type: str) -> Optional[str]:
    """Public endpoint for a service type, out of the token's catalog.

    "reservation" is Blazar; "container" is Zun. Last match wins, preserving the
    original loop: a site publishes one public endpoint per type, so a repeat is
    a duplicate rather than an alternative.
    """
    found = None
    for svc in (token_body or {}).get("token", {}).get("catalog", []):
        if svc.get("type") == service_type:
            for ep in svc.get("endpoints", []):
                if ep.get("interface") == "public":
                    found = ep["url"].rstrip("/")
    return found


def probe_site(env: Dict[str, str], rc_file: Optional[str] = None) -> dict:
    """Raw per-site result: {site, blazar, kind, nodes[], error}."""
    label = env.get("OS_REGION_NAME") or os.path.basename(rc_file or "?")
    out = {"site": label, "blazar": None, "kind": None, "nodes": [], "error": None}

    token, token_body, err = keystone_auth(env)
    if err:
        out["error"] = err
        return out

    out["blazar"] = public_endpoint(token_body, "reservation")
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


def fetch_sites(rc_glob: Optional[str] = None,
                sites: Optional[Iterable[str]] = None) -> List[dict]:
    """Probe sites whose openrc matches the glob.

    `sites` restricts to those OS_REGION_NAMEs, and is where the cost saving
    lives. Sourcing an openrc is a local subshell with no network, so we read
    every rc file to learn which site it belongs to, then pay the HTTP cost
    (auth + resources + allocations, ~6s) only for the ones asked for.
    """
    pattern = rc_glob or settings.chameleon_rc_glob
    wanted = set(sites) if sites else None
    out = []
    for p in sorted(glob.glob(os.path.expanduser(pattern or ""))):
        env = load_rc(p)
        if wanted is not None and env.get("OS_REGION_NAME") not in wanted:
            continue
        out.append(probe_site(env, p))
    return out


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
                 site: Optional[str] = None, all_sites: bool = False,
                 machine_types: Optional[Iterable[str]] = None):
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
        # machine_types wins over site: the caller has told us what hardware it
        # wants, and the catalog knows better than a default which sites carry it.
        self.machine_types = sorted({m for m in (machine_types or []) if m}) or None
        self.site = (None if (all_sites or self.machine_types)
                     else (site or settings.chi_site_name))
        self._cache: Optional[List[dict]] = None
        self._probed: List[str] = []
        self._fetched_at = 0.0

    def _target_sites(self) -> Optional[List[str]]:
        """Sites worth contacting. None means "no idea, sweep everything"."""
        if self.machine_types:
            from ..inventory.catalog import InventoryCache
            known = InventoryCache().sites_for_types(self.machine_types)
            # Empty means the catalog has never seen these types. Pruning on
            # that would silently return "nothing free" for real hardware, so
            # fall back to the full sweep and let the caller pay once.
            if known:
                return known
            log.warning("no catalog entry for %s; falling back to a full sweep",
                        self.machine_types)
        return [self.site] if self.site else None

    def _sites(self) -> List[dict]:
        # The cache used to live for the lifetime of the process. That is fine
        # for a one-shot CLI run and wrong for a long-running chatbot, which
        # would answer every question from the state it saw at start-up while
        # presenting it as current. A short TTL keeps a single question's
        # several calls on one fetch without ever serving hour-old state.
        import os
        import time

        ttl = float(os.environ.get("BLAZAR_CACHE_TTL", "60"))
        now = time.monotonic()
        if self._cache is not None and now - self._fetched_at > ttl:
            self._cache = None
            self._probed = []
        if self._cache is None:
            targets = self._target_sites()
            self._cache = fetch_sites(self.rc_glob, sites=targets)
            self._probed = [s["site"] for s in self._cache]
            self._fetched_at = now
        return self._cache

    def _extend_for(self, machine_types: Iterable[str]) -> None:
        """Fetch sites for types we did not originally ask for.

        The guard against a silent wrong answer: if the reasoner picks a type
        outside the candidate set, an empty availability list makes
        device_free_in_window fail and turns a good recommendation into exit 1.
        One extra targeted fetch (~6s, usually one site) is the cheaper error.
        """
        from ..inventory.catalog import InventoryCache
        extra = [s for s in InventoryCache().sites_for_types(machine_types)
                 if s not in self._probed]
        if not extra:
            return
        log.info("extending availability fetch to %s for %s",
                 extra, sorted(set(machine_types)))
        self._cache = (self._cache or []) + fetch_sites(self.rc_glob, sites=extra)
        self._probed += extra

    def _nodes(self) -> List[dict]:
        nodes = [n for s in self._sites() if not s["error"] for n in s["nodes"]]
        if self.machine_types:
            return [n for n in nodes if n["node_type"] in set(self.machine_types)]
        if self.site:
            return [n for n in nodes if n["site"] == self.site]
        return nodes

    def list_devices(self, machine_type: Optional[str] = None,
                     machine_types: Optional[Iterable[str]] = None
                     ) -> List[DeviceAvailability]:
        wanted = {m for m in (machine_types or []) if m}
        if machine_type:
            wanted.add(machine_type)
        if wanted:
            self._sites()  # ensure the first fetch happened before diffing
            missing = wanted - {n["node_type"] for n in self._all_nodes()}
            if missing:
                self._extend_for(missing)
        nodes = self._all_nodes() if wanted else self._nodes()
        return [to_availability(n) for n in nodes
                if not wanted or n["node_type"] in wanted]

    def _all_nodes(self) -> List[dict]:
        """Every node fetched so far, before site/type scoping."""
        return [n for s in self._sites() if not s["error"] for n in s["nodes"]]

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
            "scoped_to": (f"types {self.machine_types}" if self.machine_types
                          else self.site or "all sites"),
            "sites_probed": self._probed,
            "devices": len(nodes),
            "free_now": sum(n["status"] == "free" for n in nodes),
            "down": sum(n["status"] == "down" for n in nodes),
        }
