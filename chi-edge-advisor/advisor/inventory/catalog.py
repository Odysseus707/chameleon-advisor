"""Static CHI@Edge hardware catalog: device types, arch, GPU, peripherals.

The probe (probe_availability.py) established that the reference API exposes NO
CHI@Edge inventory, so the authoritative source for the edge catalog is
python-chi (`hardware.get_devices`). When python-chi is unavailable (offline /
no credentials) we fall back to a small curated catalog distilled from the
seeded Trovi artifacts. Either way the result is cached to JSON and refreshable
on demand.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..config import settings


@dataclass
class DeviceType:
    """One CHI@Edge machine_type and its capabilities."""

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


# --- Curated fallback catalog -------------------------------------------------
# Distilled from the seeded artifacts + CHI@Edge docs. Treated as a floor, not
# ground truth; a python-chi refresh supersedes it. device_profiles/peripherals
# are exactly those exercised by the grounding notebooks.
CURATED_CATALOG: List[DeviceType] = [
    DeviceType(
        machine_type="raspberrypi4-64",
        architecture="arm64",
        gpu=False,
        device_profiles=["pi_libcamera", "pi_sensehat", "pi_gpio"],
        peripherals=["camera", "sense_hat", "gpio", "i2c"],
        example_devices=["iot-rpi4-picam2", "iot-rpi4-picam3", "iot-rpi-cm4-02"],
        runtime=None,
        platform_version=2,
        notes="Most common CHI@Edge device; camera/sensor artifacts target it.",
    ),
    DeviceType(
        machine_type="raspberrypi3",
        architecture="arm",
        gpu=False,
        device_profiles=["pi_gpio"],
        peripherals=["gpio", "i2c"],
        example_devices=[],
        platform_version=2,
        notes="Older 32-bit Pi; limited memory.",
    ),
    DeviceType(
        machine_type="jetson-nano",
        architecture="arm64",
        gpu=True,
        device_profiles=[],
        peripherals=["gpu", "csi_camera"],
        example_devices=[],
        runtime="nvidia",
        platform_version=2,
        notes="GPU workloads REQUIRE runtime=nvidia. arm64 image required.",
    ),
    DeviceType(
        machine_type="jetson-xavier-nx",
        architecture="arm64",
        gpu=True,
        device_profiles=[],
        peripherals=["gpu"],
        example_devices=[],
        runtime="nvidia",
        platform_version=2,
        notes="GPU workloads REQUIRE runtime=nvidia. arm64 image required.",
    ),
    DeviceType(
        machine_type="jetson-agx-xavier",
        architecture="arm64",
        gpu=True,
        device_profiles=[],
        peripherals=["gpu"],
        example_devices=[],
        runtime="nvidia",
        platform_version=2,
        notes="GPU workloads REQUIRE runtime=nvidia. arm64 image required.",
    ),
    DeviceType(
        machine_type="nvidia-jetson-agx-orin",
        architecture="arm64",
        gpu=True,
        device_profiles=[],
        peripherals=["gpu"],
        example_devices=[],
        runtime="nvidia",
        platform_version=2,
        notes="High-end Jetson; GPU workloads REQUIRE runtime=nvidia.",
    ),
]


class InventoryCache:
    """Fetch, cache, and query the CHI@Edge static catalog."""

    def __init__(self, cache_path: Optional[Path] = None):
        self.cache_path = Path(cache_path or settings.inventory_cache_path)
        self._catalog: List[DeviceType] = []

    # -- loading ----------------------------------------------------------
    def load(self, refresh: bool = False) -> List[DeviceType]:
        """Return the catalog, using cache unless ``refresh`` is set."""
        if self._catalog and not refresh:
            return self._catalog
        if not refresh and self.cache_path.is_file():
            self._catalog = self._read_cache()
            if self._catalog:
                return self._catalog
        self._catalog = self._fetch()
        self._write_cache(self._catalog)
        return self._catalog

    def refresh(self) -> List[DeviceType]:
        return self.load(refresh=True)

    def _read_cache(self) -> List[DeviceType]:
        try:
            raw = json.loads(self.cache_path.read_text())
            return [DeviceType(**d) for d in raw.get("device_types", [])]
        except Exception:  # noqa: BLE001 - corrupt cache => refetch
            return []

    def _write_cache(self, catalog: List[DeviceType]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": getattr(self, "_source", "unknown"),
            "device_types": [asdict(d) for d in catalog],
        }
        self.cache_path.write_text(json.dumps(payload, indent=2))

    def _fetch(self) -> List[DeviceType]:
        """Prefer python-chi; fall back to the curated catalog."""
        if not settings.offline:
            live = self._fetch_from_chi()
            if live:
                self._source = "python-chi"
                return live
        self._source = "curated_fallback"
        return list(CURATED_CATALOG)

    def _fetch_from_chi(self) -> List[DeviceType]:
        try:
            import chi  # noqa: F401
            from chi import hardware
        except Exception:  # noqa: BLE001
            return []
        try:
            chi.use_site(settings.chi_site_name)
            devices = hardware.get_devices()
        except Exception:  # noqa: BLE001 - no creds / offline
            return []
        by_type: Dict[str, DeviceType] = {}
        for dev in devices:
            mtype = getattr(dev, "device_type", None) or "unknown"
            arch = getattr(dev, "architecture", None) or "unknown"
            gpu = bool(getattr(dev, "gpu", False))
            dt = by_type.setdefault(
                mtype,
                DeviceType(
                    machine_type=mtype,
                    architecture=arch,
                    gpu=gpu,
                    runtime="nvidia" if gpu else None,
                ),
            )
            name = getattr(dev, "device_name", None)
            if name and name not in dt.example_devices:
                dt.example_devices.append(name)
        return list(by_type.values())

    # -- queries ----------------------------------------------------------
    def get(self, machine_type: str) -> Optional[DeviceType]:
        for dt in self.load():
            if dt.machine_type == machine_type:
                return dt
        return None

    def machine_types(self) -> List[str]:
        return [dt.machine_type for dt in self.load()]

    def all_device_profiles(self) -> List[str]:
        seen: List[str] = []
        for dt in self.load():
            for p in dt.device_profiles:
                if p not in seen:
                    seen.append(p)
        return seen
