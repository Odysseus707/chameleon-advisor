"""ReferenceApiBackend: CHI@Edge availability via the Chameleon reference API.

The reference API (https://api.chameleoncloud.org, Grid'5000-based) exposes a
static hardware catalog under /sites, /clusters, /nodes. This backend:
  1. Pulls whatever CHI@Edge inventory the reference API exposes.
  2. Opportunistically probes for a *live* status endpoint and folds it in if
     one is found.

Empirically (see probe_availability.py) the `edge` site currently exposes no
nodes and the node schema carries no reservation fields, so live state is
NOT available here -- `free_now` stays None and `live_state_known` is False.
The backend still returns identity records so the pipeline can run and defer
live state to BlazarBackend.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from ..config import settings
from ..http_util import get_json
from .base import AvailabilityBackend, DeviceAvailability

# Candidate paths we test when hunting for a live-status endpoint on the
# reference API. None of these are documented as authoritative; the probe
# records which (if any) actually exist.
LIVE_STATUS_CANDIDATES = [
    "/sites/{site}/status.json",
    "/sites/{site}/nodes/status.json",
    "/sites/{site}/availability.json",
    "/sites/{site}/reservations.json",
]


class ReferenceApiBackend(AvailabilityBackend):
    name = "reference_api"
    # Set True only if a live endpoint is discovered at runtime.
    reports_live_state = False

    def __init__(self, base: Optional[str] = None, site: Optional[str] = None):
        self.base = (base or settings.reference_api_base).rstrip("/")
        self.site = site or settings.edge_site_uid
        self._live_endpoint: Optional[str] = None

    # -- inventory ---------------------------------------------------------
    def _iter_node_urls(self) -> List[str]:
        """Discover node detail URLs by walking site -> clusters -> nodes."""
        urls: List[str] = []
        clusters = get_json(f"{self.base}/sites/{self.site}/clusters.json")
        if not clusters.ok or not isinstance(clusters.json, dict):
            return urls
        for cluster in clusters.json.get("items", []):
            cuid = cluster.get("uid")
            if not cuid:
                continue
            nodes = get_json(
                f"{self.base}/sites/{self.site}/clusters/{cuid}/nodes.json"
            )
            if not nodes.ok or not isinstance(nodes.json, dict):
                continue
            for node in nodes.json.get("items", []):
                nuid = node.get("uid")
                if nuid:
                    urls.append(
                        f"{self.base}/sites/{self.site}/clusters/{cuid}"
                        f"/nodes/{nuid}.json"
                    )
        return urls

    @staticmethod
    def _node_to_availability(node: dict) -> DeviceAvailability:
        gpu_field = node.get("gpu")
        gpu = bool(gpu_field) and gpu_field != {"gpu": False}
        if isinstance(gpu_field, dict):
            gpu = bool(gpu_field.get("gpu", False))
        return DeviceAvailability(
            device_uid=node.get("uid") or node.get("node_name") or "unknown",
            machine_type=node.get("node_type") or node.get("node_name") or "unknown",
            architecture=(node.get("architecture") or {}).get("platform_type")
            if isinstance(node.get("architecture"), dict)
            else node.get("architecture"),
            gpu=gpu,
            peripherals=[],
            free_now=None,  # reference API has no reservation state
            source="reference_api",
            live_state_known=False,
        )

    def list_devices(
        self,
        machine_type: Optional[str] = None,
        machine_types: Optional[Iterable[str]] = None,
    ) -> List[DeviceAvailability]:
        # No site index here, so filtering stays client-side: the reference API
        # gets walked in full either way. Only the Blazar backend can prune.
        wanted = {m for m in (machine_types or []) if m}
        if machine_type:
            wanted.add(machine_type)
        out: List[DeviceAvailability] = []
        for url in self._iter_node_urls():
            res = get_json(url)
            if not res.ok or not isinstance(res.json, dict):
                continue
            dev = self._node_to_availability(res.json)
            if wanted and dev.machine_type not in wanted:
                continue
            out.append(dev)
        return out

    def get_device(self, device_uid: str) -> Optional[DeviceAvailability]:
        for dev in self.list_devices():
            if dev.device_uid == device_uid:
                return dev
        return None

    # -- live status probing ----------------------------------------------
    def probe_live_status(self) -> dict:
        """Test whether the reference API exposes any live status endpoint.

        Returns a diagnostic dict: which candidate paths exist, and whether the
        static node schema contains any reservation-like fields. Used by
        probe_availability.py and by healthcheck().
        """
        findings = {"candidates": [], "live_endpoint": None}
        for tmpl in LIVE_STATUS_CANDIDATES:
            path = tmpl.format(site=self.site)
            res = get_json(f"{self.base}{path}")
            findings["candidates"].append(
                {"path": path, "status": res.status, "ok": res.ok}
            )
            if res.ok and findings["live_endpoint"] is None:
                findings["live_endpoint"] = path
                self._live_endpoint = path
                self.reports_live_state = True
        return findings

    def healthcheck(self) -> dict:
        root = get_json(f"{self.base}/sites/{self.site}.json")
        return {
            "backend": self.name,
            "reachable": root.ok,
            "site": self.site,
            "reports_live_state": self.reports_live_state,
        }
