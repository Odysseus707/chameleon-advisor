"""Structured recommendation schema shared by reason/validate/emit."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Recommendation:
    """The advisor's concrete, checkable recommendation."""

    machine_type: str
    count: int
    duration_hours: int
    architecture: str
    image: str
    reasoning: str

    # optional / trap-relevant fields
    device_name: Optional[str] = None  # specific host, when peripheral-bound
    device_profiles: List[str] = field(default_factory=list)
    platform_version: int = 2
    runtime: Optional[str] = None  # "nvidia" for Jetson GPU workloads
    exposed_ports: List[int] = field(default_factory=list)
    gpu: bool = False

    # Which site to provision on, and which python-chi grammar that site needs.
    # api_family selects the emitter template, so it is copied from the resource
    # catalog (observed from Blazar) rather than guessed: a wrong value renders
    # a spec that fails at submission.
    site: Optional[str] = None
    api_family: str = "edge"  # "edge" | "kvm" | "baremetal"

    # Ranked fallbacks, best first, excluding machine_type itself. The
    # reservation benchmark grades a top-3 rather than a single pick, because a
    # recommendation whose only option is unreservable is not actionable.
    alternatives: List[str] = field(default_factory=list)

    # Which rung of the selection ladder produced this, when the ladder
    # produced it at all ("" for the edge reasoner path). A recommendation
    # that matched immediately is a different claim from one that reached the
    # fourth rung, and the reader is entitled to know which they got:
    #   free_now                free hardware, right now
    #   future                  nothing free; this frees up in wait_hours
    #   no_host_state           KVM: flavors are not reserved per host
    #   infeasible_capability   no hardware here can do it
    #   infeasible_busy         hardware exists and fits, all of it is taken
    selection_rung: str = ""
    # Constraints the advisor supplied rather than the user. Always surfaced:
    # a recommendation resting on "we assumed you need 80 GB of VRAM" is a
    # different claim from one resting on the user having said so.
    assumptions: List[str] = field(default_factory=list)
    # Hours until the recommendation becomes actionable. None means now.
    wait_hours: Optional[float] = None

    # provenance: artifact_ids that grounded this recommendation
    grounded_by: List[str] = field(default_factory=list)
    # which reasoner produced it: "tejas" | "anthropic" | "heuristic"
    produced_by: str = "unknown"

    @classmethod
    def from_dict(cls, data: dict) -> "Recommendation":
        """Build from an LLM's JSON, tolerating missing/renamed keys."""
        def pick(*names, default=None):
            for n in names:
                if n in data and data[n] is not None:
                    return data[n]
            return default

        return cls(
            machine_type=pick("machine_type", "device", "device_type", default="unknown"),
            count=int(pick("count", default=1)),
            duration_hours=int(pick("duration_hours", "duration", default=3)),
            architecture=pick("architecture", "arch", default="unknown"),
            image=pick("image", "image_ref", default=""),
            reasoning=pick("reasoning", "rationale", default=""),
            device_name=pick("device_name"),
            device_profiles=list(pick("device_profiles", default=[]) or []),
            platform_version=int(pick("platform_version", default=2)),
            runtime=pick("runtime"),
            exposed_ports=list(pick("exposed_ports", default=[]) or []),
            gpu=bool(pick("gpu", default=False)),
            site=pick("site"),
            api_family=pick("api_family", default="edge"),
            alternatives=list(pick("alternatives", "fallbacks", default=[]) or []),
            selection_rung=pick("selection_rung", default="") or "",
            assumptions=list(pick("assumptions", default=[]) or []),
            wait_hours=pick("wait_hours"),
            grounded_by=list(pick("grounded_by", "artifact_ids", default=[]) or []),
            produced_by=pick("produced_by", default="unknown"),
        )
