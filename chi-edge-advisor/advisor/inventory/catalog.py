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

#: Bump when the SHAPE or POPULATION of the catalog changes, not on every edit.
#: A cache written before the bare-metal types existed is not merely old, it is
#: a different catalog - and staleness-by-age never notices, because the file
#: is perfectly fresh. The symptom is an advisor that answers
#: "nothing at CHI@TACC can do this" while holding only CHI@Edge hardware.
#:   1  edge only, 7 device types
#:   2  + 29 bare-metal node types, + vcpus/gpu_model/covered_by
CATALOG_SCHEMA_VERSION = 2


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

    # -- hardware capability ------------------------------------------------
    # Blazar reports none of this. It is vendor specification, hand-curated,
    # and it is what lets a recommendation reject hardware that is free but
    # cannot run the workload. Without it `gpu` is the only signal, and a
    # jetson-nano (compute 5.3) is indistinguishable from an AGX Orin (8.7).
    #
    # accelerator is the field that does the most work:
    #   "none"    - CPU only.
    #   "cuda"    - NVIDIA GPU, needs runtime="nvidia".
    #   "edgetpu" - Google Edge TPU. int8-quantised TFLite ONLY; CUDA code will
    #               not run on it. This is the accelerator-confusion trap.
    accelerator: Optional[str] = None
    soc: str = ""
    cuda_compute: Optional[float] = None
    cuda_cores: int = 0
    tensor_cores: int = 0
    dla_cores: int = 0
    edge_tpu_tops: Optional[float] = None
    ram_gb: Optional[int] = None
    precisions: List[str] = field(default_factory=list)
    storage: str = ""

    # -- bare-metal capability (chameleon wing) -----------------------------
    # vcpus is required by the reservation solver's `meets()`; without it a
    # min_vcpus requirement silently passes on every node.
    #
    # None here means NOT MEASURED, and that is not the same as zero. Blazar
    # reported nothing for 17 of the 29 bare-metal types, so a null must FAIL
    # a minimum rather than satisfy it - an absent measurement is not a
    # measurement of absence.
    vcpus: Optional[int] = None
    microarchitecture: str = ""
    gpu_model: Optional[str] = None
    gpu_per_node: int = 0
    vram_gb_per_gpu: Optional[int] = None
    # Artifacts whose grounding names this type. PROVENANCE ONLY. Capability
    # never comes from an artifact: an artifact may say a type exists, it may
    # never say what the hardware can do.
    covered_by: List[str] = field(default_factory=list)


def _known_fields() -> set:
    return {f.name for f in fields(DeviceType)}


# --- Curated fallback catalog -------------------------------------------------
# The seven device types that actually exist on CHI@Edge, with vendor hardware
# specifications. A floor, not ground truth: a live Blazar sweep supersedes the
# topology fields and adds the non-edge sites, but Blazar reports no
# capabilities at all, so the specs below stay authoritative (see the merge in
# _fetch_from_blazar).
#
# The machine_type strings are the ones Blazar actually returns. An earlier
# revision carried four names that do not exist on the site
# (jetson-agx-xavier, jetson-xavier-nx, nvidia-jetson-agx-orin, raspberrypi3)
# and was missing four that do, so the static inventory contradicted live
# availability in the same prompt.
#
# Specs are vendor facts. Deliberately NOT recorded here: which artifact covers
# a type (that comes from the artifact registry) and any ranking or scoring
# rule. Selection logic lives in the reasoner, not in the data.
CURATED_CATALOG: List[DeviceType] = [
    DeviceType(
        machine_type="raspberrypi4-64",
        architecture="arm64",
        gpu=False,
        accelerator="none",
        soc="BCM2711 (Cortex-A72 quad @ 1.5GHz)",
        ram_gb=8,
        precisions=["fp32", "int8"],          # int8 via TFLite on CPU
        storage="sdcard",
        device_profiles=["pi_libcamera", "pi_sensehat", "pi_gpio"],
        peripherals=["camera", "gpio", "i2c", "sense_hat"],
        example_devices=["candlestick1-pi4", "ft-rpi4-3", "iot-rpi-cm4-02"],
        sites=["CHI@Edge"],
        api_family="edge",
        node_count=36,
        notes="The most common and best-documented type on the site. That makes "
              "it the artifact-bias trap: an artifact-anchored system reaches "
              "for it even when the workload needs an accelerator it lacks.",
    ),
    DeviceType(
        machine_type="raspberrypi5",
        architecture="arm64",
        gpu=False,
        accelerator="none",
        soc="BCM2712 (Cortex-A76 quad @ 2.4GHz)",
        ram_gb=8,
        precisions=["fp32", "int8"],
        storage="sdcard",
        device_profiles=[],                   # no profile strings verified yet
        peripherals=["camera", "gpio", "i2c"],
        example_devices=["iot-rpi5-nvme-01", "nyu-rpi5-01"],
        sites=["CHI@Edge"],
        api_family="edge",
        node_count=10,
        notes="Roughly 2-3x the CPU inference throughput of the Pi 4. Still no "
              "accelerator.",
    ),
    DeviceType(
        machine_type="jetson-nano",
        architecture="arm64",
        gpu=True,
        accelerator="cuda",
        soc="Tegra X1 (Cortex-A57 quad)",
        cuda_compute=5.3,
        cuda_cores=128,
        ram_gb=4,
        precisions=["fp32", "fp16"],          # no int8 path
        runtime="nvidia",
        storage="sdcard",
        peripherals=["camera", "gpio", "i2c"],
        example_devices=["ft-nano-1", "iot-jetson01"],
        sites=["CHI@Edge"],
        api_family="edge",
        node_count=12,
        notes="Entry-level Jetson. CUDA, but compute 5.3 and no tensor cores: "
              "it fails workloads that need modern CUDA or int8.",
    ),
    DeviceType(
        machine_type="jetson-xavier-nx-devkit-emmc",
        architecture="arm64",
        gpu=True,
        accelerator="cuda",
        soc="Xavier NX",
        cuda_compute=7.2,
        cuda_cores=384,
        tensor_cores=48,
        dla_cores=2,
        ram_gb=8,
        precisions=["fp32", "fp16", "int8"],
        runtime="nvidia",
        storage="emmc",
        peripherals=["camera", "gpio", "i2c"],
        example_devices=["iot-xavier-nx-01", "iot-xavier-nx-02"],
        sites=["CHI@Edge"],
        api_family="edge",
        node_count=4,
    ),
    DeviceType(
        machine_type="jetson-orin-nano-devkit-nvme",
        architecture="arm64",
        gpu=True,
        accelerator="cuda",
        soc="Orin Nano",
        cuda_compute=8.7,
        cuda_cores=1024,
        tensor_cores=32,
        ram_gb=8,
        precisions=["fp32", "fp16", "int8"],
        runtime="nvidia",
        storage="nvme",
        peripherals=["camera", "gpio", "i2c"],
        example_devices=["iot-orin-nano-01", "iot-orin-nano-02"],
        sites=["CHI@Edge"],
        api_family="edge",
        node_count=3,
    ),
    DeviceType(
        machine_type="jetson-agx-orin-devkit-64gb",
        architecture="arm64",
        gpu=True,
        accelerator="cuda",
        soc="AGX Orin 64GB",
        cuda_compute=8.7,
        cuda_cores=2048,
        tensor_cores=64,
        dla_cores=2,
        ram_gb=64,
        precisions=["fp32", "fp16", "int8"],
        runtime="nvidia",
        storage="nvme",
        peripherals=["camera", "gpio", "i2c"],
        example_devices=["iot-agx-orin-01"],
        sites=["CHI@Edge"],
        api_family="edge",
        node_count=1,
        notes="The most capable part on the site, and the scarcest: one unit.",
    ),
    DeviceType(
        machine_type="coral-dev",
        architecture="arm64",
        gpu=False,                            # an accelerator, but not a GPU
        accelerator="edgetpu",
        soc="NXP i.MX8M (Cortex-A53 quad)",
        edge_tpu_tops=4.0,
        ram_gb=1,
        precisions=["int8"],                  # int8-quantised TFLite only
        storage="emmc",
        peripherals=["camera", "gpio", "i2c"],
        example_devices=["nyu-coral-01", "nyu-coral-02"],
        sites=["CHI@Edge"],
        api_family="edge",
        node_count=2,
        notes="Accelerator-confusion trap: matching on the word 'accelerator' "
              "picks it, but CUDA code cannot run on an Edge TPU and anything "
              "not int8-quantised cannot run on it either.",
    ),
]


# --- bare-metal capability table (chameleon wing) -----------------------------
# Cache keyed by path, never a bare lru_cache over a no-argument function: an
# unkeyed cache of a per-wing table grades the second wing against the first.
_CAPTABLE_CACHE: Dict[str, List[DeviceType]] = {}


def capability_table_types(path: Optional[Path] = None) -> List[DeviceType]:
    """The 29 bare-metal node types, read from the benchmark's table.

    This table is the ONLY authority on what bare-metal hardware can do (R3).
    Blazar reports which hosts exist and whether they are free; it reports
    almost nothing about their capability, and 18 of these 29 types are named
    by no artifact at all - for those, "correct" is defined by this file and
    nothing else.

    Every one of the 29 is bare metal at CHI@UC or CHI@TACC. `kvm_compute` is
    a CHI@TACC bare-metal node type despite the name, not a KVM flavor;
    KVM@TACC has no entry here at all, because KVM reserves flavors rather
    than hosts and a per-host capability row would not answer any question
    anyone can ask of it.
    """
    path = Path(path or (settings.corpus_dir / "capability_table.yaml"))
    key = str(path)
    hit = _CAPTABLE_CACHE.get(key)
    if hit is not None:
        return [DeviceType(**asdict(d)) for d in hit]
    if not path.is_file():
        log.info("no bare-metal capability table at %s; edge types only", path)
        return []
    try:
        import yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))["node_types"]
    except Exception as exc:  # noqa: BLE001
        log.warning("capability table unreadable (%s); edge types only", exc)
        return []

    out: List[DeviceType] = []
    for name, spec in raw.items():
        sites = dict(spec.get("sites") or {})
        accel = spec.get("accelerator")
        out.append(DeviceType(
            machine_type=name,
            architecture=spec.get("architecture") or "x86_64",
            # `gpu` is the coarse legacy flag. An MI100 IS a GPU even though
            # CUDA will not run on it, so this must not be read as "cuda":
            # `accelerator` carries that distinction and the emitter and the
            # capability filter both use it, not this.
            gpu=accel in {"cuda", "rocm", "oneapi"},
            accelerator=accel,
            # runtime="nvidia" is a CHI@Edge container concern. Bare metal
            # boots a whole machine, so there is no container runtime to set.
            runtime=None,
            sites=sorted(sites),
            node_count=sum(sites.values()),
            api_family="baremetal",
            cuda_compute=spec.get("cuda_compute"),
            cuda_cores=spec.get("cuda_cores") or 0,
            tensor_cores=spec.get("tensor_cores") or 0,
            ram_gb=spec.get("ram_gb"),
            vcpus=spec.get("vcpus"),
            precisions=list(spec.get("precisions") or []),
            microarchitecture=spec.get("microarchitecture") or "",
            gpu_model=spec.get("gpu_model"),
            gpu_per_node=spec.get("gpu_per_node") or 0,
            vram_gb_per_gpu=spec.get("vram_gb_per_gpu"),
            covered_by=list(spec.get("covered_by") or []),
            notes=spec.get("notes") or "",
        ))
    out.sort(key=lambda d: d.machine_type)
    _CAPTABLE_CACHE[key] = out
    return [DeviceType(**asdict(d)) for d in out]


def capability_ranking_weights(path: Optional[Path] = None) -> Dict[str, int]:
    """The testbed's own capability-score weights, from the table.

    Read rather than hardcoded so the advisor ranks hardware by the same rule
    the benchmark's golds were solved with. Inventing a second ranking policy
    here would make every disagreement unattributable: you could not tell a
    worse recommendation from a differently-weighted one.
    """
    path = Path(path or (settings.corpus_dir / "capability_table.yaml"))
    default = {"cuda_cores": 1, "tensor_cores": 4, "ram_gb": 8, "vcpus": 4}
    if not path.is_file():
        return dict(default)
    try:
        import yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return dict(raw["ranking"]["capability_score"])
    except Exception as exc:  # noqa: BLE001
        log.warning("capability ranking unreadable (%s); using defaults", exc)
        return dict(default)


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
            if raw.get("schema_version") != CATALOG_SCHEMA_VERSION:
                log.info("resource catalog is schema v%s, want v%s; refreshing",
                         raw.get("schema_version"), CATALOG_SCHEMA_VERSION)
                return True
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
            "schema_version": CATALOG_SCHEMA_VERSION,
            "source": getattr(self, "_source", "unknown"),
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "device_types": [asdict(d) for d in catalog],
        }
        self.cache_path.write_text(json.dumps(payload, indent=2))

    @staticmethod
    def _static_capability() -> Dict[str, DeviceType]:
        """Everything we know about hardware that Blazar cannot tell us.

        Two sources, one shape: the curated edge specs and the benchmark's
        bare-metal capability table. Neither is ever superseded by a live
        sweep, because a live sweep has no opinion on capability at all.
        """
        by_type = {d.machine_type: d for d in CURATED_CATALOG}
        for d in capability_table_types():
            # Edge wins a name collision. There is none today; if one appears,
            # silently reclassifying an edge device as bare metal would change
            # which emitter grammar it gets, so say so.
            if d.machine_type in by_type:
                log.warning("machine_type %s is in both the curated edge "
                            "catalog and the bare-metal capability table; "
                            "keeping the edge entry", d.machine_type)
                continue
            by_type[d.machine_type] = d
        return by_type

    def _fetch(self) -> List[DeviceType]:
        """Prefer a live Blazar sweep; fall back to the static catalogue."""
        if not settings.offline:
            live = self._fetch_from_blazar()
            if live:
                self._source = "blazar"
                return live
        self._source = "static_fallback"
        return sorted(self._static_capability().values(),
                      key=lambda d: d.machine_type)

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

        # Blazar exposes no device_profiles or peripherals, so a live sweep on
        # its own silently empties them and device_profile_exists then rejects
        # a perfectly good pi_libcamera recommendation. The sweep is
        # authoritative for topology (sites, counts, api_family, arch, gpu);
        # the curated entries stay authoritative for capabilities Blazar cannot
        # see. Merge rather than replace.
        static = self._static_capability()
        for dt in by_type.values():
            c = static.get(dt.machine_type)
            if c is None:
                continue
            dt.device_profiles = dt.device_profiles or list(c.device_profiles)
            dt.peripherals = dt.peripherals or list(c.peripherals)
            dt.notes = dt.notes or c.notes
            dt.platform_version = c.platform_version
            dt.runtime = dt.runtime or c.runtime
            # Hardware capability is vendor specification. Blazar has no opinion
            # on it, so unlike the fields above there is nothing live to prefer:
            # take curated unconditionally. Omitting these here is exactly the
            # bug the comment above describes, one field set later.
            dt.accelerator = c.accelerator
            dt.soc = c.soc
            dt.cuda_compute = c.cuda_compute
            dt.cuda_cores = c.cuda_cores
            dt.tensor_cores = c.tensor_cores
            dt.dla_cores = c.dla_cores
            dt.edge_tpu_tops = c.edge_tpu_tops
            dt.ram_gb = c.ram_gb
            dt.precisions = list(c.precisions)
            dt.storage = c.storage
            dt.vcpus = c.vcpus
            dt.microarchitecture = c.microarchitecture
            dt.gpu_model = c.gpu_model
            dt.gpu_per_node = c.gpu_per_node
            dt.vram_gb_per_gpu = c.vram_gb_per_gpu
            dt.covered_by = list(c.covered_by)
            # runtime="nvidia" is a container concern and the live sweep sets
            # it from the gpu flag alone. Bare metal boots a whole machine;
            # there is no container runtime, and emitting one is noise.
            if dt.api_family == "baremetal":
                dt.runtime = None

        # A site we could not reach reports no types, and dropping its
        # hardware entirely would let the advisor answer "nothing exists"
        # when the truth is "we could not look". Static entries the sweep did
        # not cover are added back with node_count 0 - present, but making no
        # claim about how many are there.
        for name, c in static.items():
            if name not in by_type:
                missing = DeviceType(**asdict(c))
                missing.node_count = 0
                by_type[name] = missing

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
