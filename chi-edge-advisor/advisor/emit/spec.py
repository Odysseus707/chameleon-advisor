"""Emitter: turn a validated Recommendation into a runnable python-chi spec.

Uses the object-oriented python-chi style required for CHI@Edge:
  - lease.Lease(...).add_device_reservation(...)  (NOT add_node_reservation)
  - container.Container(...)                       (NOT create_server)

`dry_check` constructs the lease/container objects WITHOUT submitting them, to
confirm the spec is structurally valid. If python-chi is installed it builds the
real objects (never calling .submit()); otherwise it validates the required
fields structurally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..reason.schema import Recommendation


@dataclass
class DryCheckResult:
    passed: bool
    mode: str  # "python-chi" | "structural"
    details: List[str] = field(default_factory=list)


def _safe_name(rec: Recommendation) -> str:
    # CHI@Edge uses Kubernetes -> no underscores in container names.
    base = (rec.device_name or rec.machine_type).replace("_", "-")
    return f"advisor-{base}"


def render_spec(rec: Recommendation) -> str:
    """Return runnable python-chi source, dispatched on api_family.

    The three families are genuinely different grammars, not variations: edge
    reserves devices and runs containers, baremetal reserves nodes and boots
    servers, KVM reserves flavors. Emitting the wrong one produces a spec that
    fails at submission, which is why api_family is carried from the catalog
    rather than inferred here.
    """
    if rec.api_family == "baremetal":
        return _render_baremetal(rec)
    if rec.api_family == "kvm":
        return _render_kvm(rec)
    return _render_edge(rec)


def _render_baremetal(rec: Recommendation) -> str:
    """CHI@UC / CHI@TACC / CHI@NCAR / CHI@NRP / CHI@NU.

    CAUTION: add_node_reservation and create_server appear ZERO times as real
    calls anywhere in this workspace; they exist only inside benchmark
    forbidden_calls trap lists. This template comes from the python-chi API,
    not from a validated local example, and it is the first thing the
    artifact-ingestion work should ground against real notebooks.
    """
    name = _safe_name(rec)
    site = rec.site or "CHI@UC"
    image = rec.image or "CC-Ubuntu24.04"
    return f'''\
# --- chi-edge-advisor generated lease spec (baremetal) ---
# grounded_by = {rec.grounded_by}  produced_by = {rec.produced_by}
# UNVALIDATED GRAMMAR: no positive baremetal example exists in this corpus yet.
from datetime import timedelta

import chi
from chi import lease, server

chi.use_site("{site}")

# 1) Lease with a NODE reservation (baremetal uses add_node_reservation,
#    not add_device_reservation).
my_lease = lease.Lease("{name}-lease", duration=timedelta(hours={rec.duration_hours}))
my_lease.add_node_reservation(amount={rec.count}, node_type="{rec.machine_type}")
my_lease.submit(idempotent=True)

# 2) Server (baremetal boots a whole machine; there is no container here).
my_server = server.Server(
    name="{name}-node",
    reservation_id=my_lease.node_reservations[0]["id"],
    image_name="{image}",
)
my_server.submit()

# my_server.associate_floating_ip()          # if public network access needed
# my_server.delete(); my_lease.delete()      # cleanup when done
'''


def _render_kvm(rec: Recommendation) -> str:
    """KVM@TACC. Reserves a flavor rather than a node or a device."""
    name = _safe_name(rec)
    site = rec.site or "KVM@TACC"
    image = rec.image or "CC-Ubuntu24.04"
    return f'''\
# --- chi-edge-advisor generated lease spec (KVM) ---
# grounded_by = {rec.grounded_by}  produced_by = {rec.produced_by}
# UNVALIDATED GRAMMAR: only two add_flavor_reservation examples exist locally.
from datetime import timedelta

import chi
from chi import lease, server

chi.use_site("{site}")

# 1) Lease with a FLAVOR reservation (KVM reserves capacity, not a named host).
my_lease = lease.Lease("{name}-lease", duration=timedelta(hours={rec.duration_hours}))
my_lease.add_flavor_reservation(amount={rec.count}, flavor_name="{rec.machine_type}")
my_lease.submit(idempotent=True)

# 2) Virtual machine.
my_server = server.Server(
    name="{name}-vm",
    reservation_id=my_lease.flavor_reservations[0]["id"],
    image_name="{image}",
)
my_server.submit()

# my_server.associate_floating_ip()          # if public network access needed
# my_server.delete(); my_lease.delete()      # cleanup when done
'''


def _render_edge(rec: Recommendation) -> str:
    """CHI@Edge. The original path, the one grounded in real artifacts."""
    name = _safe_name(rec)
    profiles = rec.device_profiles or []
    ports = rec.exposed_ports or []

    if rec.device_name:
        reservation_line = (
            f'my_lease.add_device_reservation(\n'
            f'    amount={rec.count}, machine_type="{rec.machine_type}", '
            f'device_name="{rec.device_name}"\n)'
        )
    else:
        reservation_line = (
            f'my_lease.add_device_reservation(\n'
            f'    amount={rec.count}, machine_type="{rec.machine_type}"\n)'
        )

    container_kwargs = [
        f'    name="{name}-run",',
        f'    image_ref="{rec.image}",',
        f'    exposed_ports={ports},',
        f'    reservation_id=my_lease.device_reservations[0]["id"],',
    ]
    if profiles:
        container_kwargs.append(f"    device_profiles={profiles},")
    if rec.runtime:
        # Required for GPU workloads on Jetson devices.
        container_kwargs.append(f'    runtime="{rec.runtime}",')
    container_kwargs.append('    command=["sleep", "infinity"],')

    return f'''\
# --- chi-edge-advisor generated lease spec ---
# grounded_by = {rec.grounded_by}  produced_by = {rec.produced_by}
from datetime import timedelta

import chi
from chi import container, lease

chi.use_site("{rec.site or "CHI@Edge"}")

# 1) Lease with a DEVICE reservation (CHI@Edge uses add_device_reservation,
#    not add_node_reservation).
my_lease = lease.Lease("{name}-lease", duration=timedelta(hours={rec.duration_hours}))
{reservation_line}
my_lease.submit(idempotent=True)

# 2) Container (CHI@Edge uses container.Container, not create_server).
#    platform_version={rec.platform_version} is required on CHI@Edge.
my_container = container.Container(
{chr(10).join(container_kwargs)}
)
my_container.submit()

# ip_address = my_container.associate_floating_ip()  # if network access needed
# my_container.delete(); my_lease.delete()           # cleanup when done
'''


def dry_check(rec: Recommendation) -> DryCheckResult:
    """Construct the spec objects without submitting to confirm validity."""
    details: List[str] = []

    # Structural prerequisites first (apply to both modes).
    if not rec.image:
        details.append("missing image/image_ref")
    if not rec.machine_type or rec.machine_type == "unknown":
        details.append("missing/unknown machine_type")
    if rec.count < 1:
        details.append("count must be >= 1")
    if rec.duration_hours < 1:
        details.append("duration_hours must be >= 1")

    # Only the edge grammar gets a live object-construction check. The
    # baremetal and KVM templates have no validated local example, so building
    # their objects here would assert a correctness we have not earned; they
    # stay structural until artifact ingestion grounds them.
    if rec.api_family != "edge":
        details.insert(0, f"{rec.api_family} grammar: structural validation only "
                          "(no validated local example yet)")
        return DryCheckResult(passed=not any(
            d for d in details if not d.startswith(rec.api_family)),
            mode="structural", details=details)

    try:
        import chi  # noqa: F401
        from chi import container, lease
        from datetime import timedelta
    except Exception:  # noqa: BLE001 - python-chi not installed
        passed = not details
        details.insert(0, "python-chi not installed: structural validation only")
        return DryCheckResult(passed=passed, mode="structural", details=details)

    # python-chi present: build the objects but DO NOT submit.
    try:
        l = lease.Lease(
            f"{_safe_name(rec)}-lease", duration=timedelta(hours=rec.duration_hours)
        )
        kwargs = {"amount": rec.count, "machine_type": rec.machine_type}
        if rec.device_name:
            kwargs["device_name"] = rec.device_name
        l.add_device_reservation(**kwargs)
        details.append("lease.Lease + add_device_reservation constructed (not submitted)")
    except Exception as exc:  # noqa: BLE001
        details.append(f"lease construction failed: {exc}")

    try:
        ckwargs = dict(
            name=f"{_safe_name(rec)}-run",
            image_ref=rec.image,
            exposed_ports=rec.exposed_ports or [],
            command=["sleep", "infinity"],
        )
        if rec.device_profiles:
            ckwargs["device_profiles"] = rec.device_profiles
        if rec.runtime:
            ckwargs["runtime"] = rec.runtime
        container.Container(**ckwargs)  # constructed, never .submit()
        details.append("container.Container constructed (not submitted)")
    except Exception as exc:  # noqa: BLE001
        details.append(f"container construction failed: {exc}")

    passed = not any("failed" in d for d in details) and not any(
        d in {"missing image/image_ref", "missing/unknown machine_type"}
        for d in details
    )
    return DryCheckResult(passed=passed, mode="python-chi", details=details)
