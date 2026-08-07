"""Chameleon hardware catalog: which node/device types exist, and WHERE.

The `sites` field is the point of this module. Blazar has no server-side filter
(GET /os-hosts?node_type=... returns every host regardless), so the only way to
avoid a 7-site, 655-node, ~44s sweep is to not contact sites that cannot host
the type you want. Measured, 37 of 41 types live on exactly one site, so a
targeted fetch is ~6x cheaper. This catalog is what makes that pruning possible.

Source of truth is a full Blazar sweep via advisor.availability.blazar, the same
REST path the availability backend uses. Offline or without credentials we fall
back to CURATED_CATALOG, which is a floor and is CHI@Edge-only.

The cache carries generated_utc and refreshes itself once older than
settings.catalog_ttl_hours. Prefer running that refresh on a schedule so the
full sweep stays off the critical path of a user's advisor call.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from ..config import settings

log = logging.getLogger(__name__)


@dataclass
class DeviceType:
    """One machine_type/device_type and its capabilities, across all sites."""

    machine_type: str
    architecture: str  # "arm64" | "x86_64"
    gpu: bool
    # device_profiles selectable for this type (e.g. pi_libcamera, pi_sensehat).
    device_profiles: List[str] = field(default_factory=list)
    # peripherals physically attachable / present.
    peripherals: List[str] = field(default_factory=list)
    # known device_name examples (individual hosts of this type).
    example_devices: List[str] = field(default_factory=list)
    # container runtime required (e.g. "nvidia" for Jetson GPU workloads).
    runtime: Optional[str] = None
    platform_version: int = 2
    notes: str = ""

    # Which Chameleon sites carry this type. Drives site pruning; a type on one
    # site means six sites never get contacted.
    sites: List[str] = field(default_factory=list)
    # "edge" | "kvm" | "baremetal". Selects the emitter grammar, so it is
    # recorded from observation and never inferred at emit time.
    api_family: str = "edge"
    # Total hosts of this type across all its sites. Informational.
    node_count: int = 0


def _known_fields() -> set:
    return {f.name for f in fields(DeviceType)}


# --- Curated fallback catalog -------------------------------------------------
# Distilled from the seeded artifacts + CHI@Edge docs. A floor, not ground
# truth: a live Blazar sweep supersedes it and adds the non-edge sites.
CURATED_CATALOG: List[DeviceType] = [
    DeviceType(
        machine_type="raspberrypi4-64",
        architecture="arm64",
        gpu=False,
        device_profiles=["pi_libcamera", "pi_sensehat", "pi_gpio"],
        peripherals=["camera", "sense_hat", "gpio", "i2c"],
        example_devices=["iot-rpi4-picam2", "iot-rpi4-picam3", "iot-rpi-cm4-02"],
        sites=["CHI@Edge"],
        api_family="edge",
        notes="Most common CHI@Edge device; camera/sensor artifacts target it.",
    ),
    DeviceType(
        machine_type="raspberrypi5",
        architecture="arm64",
        gpu=False,
        peripherals=["camera", "gpio", "i2c"],
        example_devices=["nyu-rpi5-04"],
        sites=["CHI@Edge"],
        api_family="edge",
        notes="Targeted by serve-edge-chi; missing from the pre-multisite catalog.",
    ),
    DeviceType(
        machine_type="raspberrypi3",
        architecture="arm64",
        gpu=False,
        device_profiles=["pi_gpio"],
        peripherals=["gpio", "i2c"],
        sites=["CHI@Edge"],
        api_family="edge",
        notes="Older Pi generation; fewer units.",
    ),
    DeviceType(
        machine_type="jetson-nano",
        architecture="arm64",
        gpu=True,
        runtime="nvidia",
        peripherals=["camera", "gpio"],
        sites=["CHI@Edge"],
        api_family="edge",
        notes="Entry-level Jetson; nvidia container runtime required.",
    ),
    DeviceType(
        machine_type="jetson-xavier-nx",
        architecture="arm64",
        gpu=True,
        runtime="nvidia",
        sites=["CHI@Edge"],
        api_family="edge",
        notes="Mid-range Jetson.",
    ),
    DeviceType(
        machine_type="jetson-agx-xavier",
        architecture="arm64",
        gpu=True,
        runtime="nvidia",
        sites=["CHI@Edge"],
        api_family="edge",
        notes="High-end Jetson.",
    ),
    DeviceType(
        machine_type="nvidia-jetson-agx-orin",
        architecture="arm64",
        gpu=True,
        runtime="nvidia",
        sites=["CHI@Edge"],
        api_family="edge",
        notes="Newest Jetson generation.",
    ),
]


def api_family_for(site: str, resource_kind: str) -> str:
    """Which emitter grammar a site's resources use.

    Derived from what Blazar actually serves rather than guessed: CHI@Edge
    answers /devices and reserves device_type; KVM@TACC reserves flavors;
    everything else reserves bare-metal nodes.
    """
    if resource_kind == "devices":
        return "edge"
    if site.upper().startswith("KVM@"):
        return "kvm"
    return "baremetal"


class InventoryCache:
    """Fetch, cache, and query the multi-site hardware catalog."""

    def __init__(self, cache_path: Optional[Path] = None):
        self.cache_path = Path(cache_path or settings.inventory_cache_path)
        self._catalog: List[DeviceType] = []

    # -- loading ----------------------------------------------------------
    def load(self, refresh: bool = False) -> List[DeviceType]:
        """Return the catalog, refreshing on an explicit flag or a stale cache."""
        if self._catalog and not refresh:
            return self._catalog
        if not refresh and self.cache_path.is_file() and not self._is_stale():
            self._catalog = self._read_cache()
            if self._catalog:
                return self._catalog
        self._catalog = self._fetch()
        self._write_cache(self._catalog)
        return self._catalog

    def refresh(self) -> List[DeviceType]:
        return self.load(refresh=True)

    def _is_stale(self) -> bool:
        """True once the cache is older than the TTL. A missing stamp is stale."""
        ttl = getattr(settings, "catalog_ttl_hours", 168)
        if not ttl:
            return False
        try:
            raw = json.loads(self.cache_path.read_text())
            stamp = raw.get("generated_utc")
            if not stamp:
                return True
            age = datetime.now(timezone.utc) - datetime.fromisoformat(stamp)
        except (OSError, ValueError, json.JSONDecodeError):
            return True
        if age > timedelta(hours=ttl):
            log.info("resource catalog is %s old (ttl %sh); refreshing", age, ttl)
            return True
        return False

    def _read_cache(self) -> List[DeviceType]:
        """Load the cache, tolerating schema drift instead of dying silently.

        The previous version did DeviceType(**d) under a bare except, so adding
        a field to the JSON without adding it to the dataclass degraded to the
        curated fallback with no signal at all. Unknown keys are now dropped
        with a warning, and an unreadable cache says so.
        """
        try:
            raw = json.loads(self.cache_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("resource catalog unreadable (%s); refetching", exc)
            return []
        known, out, dropped = _known_fields(), [], set()
        for d in raw.get("device_types", []):
            dropped |= set(d) - known
            try:
                out.append(DeviceType(**{k: v for k, v in d.items() if k in known}))
            except TypeError as exc:
                log.warning("skipping malformed catalog entry %r: %s",
                            d.get("machine_type"), exc)
        if dropped:
            log.warning("resource catalog has unknown fields %s; ignoring them",
                        sorted(dropped))
        return out

    def _write_cache(self, catalog: List[DeviceType]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": getattr(self, "_source", "unknown"),
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "device_types": [asdict(d) for d in catalog],
        }
        self.cache_path.write_text(json.dumps(payload, indent=2))

    def _fetch(self) -> List[DeviceType]:
        """Prefer a live Blazar sweep; fall back to the curated catalog."""
        if not settings.offline:
            live = self._fetch_from_blazar()
            if live:
                self._source = "blazar"
                return live
        self._source = "curated_fallback"
        return list(CURATED_CATALOG)

    def _fetch_from_blazar(self) -> List[DeviceType]:
        """Full sweep across every site, folded into one entry per machine_type.

        This is the expensive call the catalog exists to avoid repeating, so it
        belongs on a schedule rather than in a user's request path.
        """
        try:
            from ..availability.blazar import _ARM_HINTS, _GPU_HINTS, fetch_sites
        except ImportError as exc:  # pragma: no cover
            log.warning("cannot import the blazar backend (%s)", exc)
            return []
        try:
            sites = fetch_sites()
        except Exception as exc:  # noqa: BLE001 - no creds / network down
            log.warning("blazar sweep failed (%s); using curated fallback", exc)
            return []

        by_type: Dict[str, DeviceType] = {}
        for site in sites:
            if site.get("error"):
                log.warning("site %s unavailable: %s", site["site"], site["error"])
                continue
            family = api_family_for(site["site"], site.get("kind") or "os-hosts")
            for n in site["nodes"]:
                mtype = n["node_type"]
                low = mtype.lower()
                dt = by_type.get(mtype)
                if dt is None:
                    gpu = bool(n.get("gpu_count")) or any(h in low for h in _GPU_HINTS)
                    dt = DeviceType(
                        machine_type=mtype,
                        architecture=("arm64" if any(h in low for h in _ARM_HINTS)
                                      else "x86_64"),
                        gpu=gpu,
                        runtime="nvidia" if gpu else None,
                        api_family=family,
                    )
                    by_type[mtype] = dt
                if site["site"] not in dt.sites:
                    dt.sites.append(site["site"])
                dt.node_count += 1
                name = str(n.get("name") or "")
                if name and len(dt.example_devices) < 3 \
                        and name not in dt.example_devices:
                    dt.example_devices.append(name)

        # A type spanning both an edge and a non-edge site would make emitter
        # dispatch ambiguous. It does not happen today; say so if it starts.
        for dt in by_type.values():
            dt.sites.sort()
            families = {api_family_for(s, "devices" if s == "CHI@Edge" else "os-hosts")
                        for s in dt.sites}
            if len(families) > 1:
                log.warning("machine_type %s spans api_families %s; emitter "
                            "dispatch will be ambiguous",
                            dt.machine_type, sorted(families))
        return sorted(by_type.values(), key=lambda d: d.machine_type)

    # -- queries ----------------------------------------------------------
    def get(self, machine_type: str) -> Optional[DeviceType]:
        for dt in self.load():
            if dt.machine_type == machine_type:
                return dt
        return None

    def machine_types(self) -> List[str]:
        return [dt.machine_type for dt in self.load()]

    def sites_for_types(self, machine_types: Iterable[str]) -> List[str]:
        """Sites that could host any of these types. Empty means "unknown".

        Callers must treat empty as "do not prune, sweep everything" rather than
        "no sites": an unrecognised type is exactly the case where guessing
        wrong silently loses the answer.
        """
        wanted = {m for m in machine_types if m}
        if not wanted:
            return []
        out: List[str] = []
        for dt in self.load():
            if dt.machine_type in wanted:
                for s in dt.sites:
                    if s not in out:
                        out.append(s)
        return sorted(out)

    def all_sites(self) -> List[str]:
        out: List[str] = []
        for dt in self.load():
            for s in dt.sites:
                if s not in out:
                    out.append(s)
        return sorted(out)

    def all_device_profiles(self) -> List[str]:
        seen: List[str] = []
        for dt in self.load():
            for p in dt.device_profiles:
                if p not in seen:
                    seen.append(p)
        return seen
