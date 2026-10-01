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
    """CHI@UC / CHI@TACC. Reserve a node, then boot a server onto it.

    VERIFIED LIVE on CHI@TACC (project CHI-231225): add_node_reservation then
    reservation_id=my_lease.node_reservations[0]["id"] submits and boots. Note
    that the reservation id and the lease id are different identifiers and the
    call accepts either shape - passing the lease id is the documented trap,
    and it fails only when the instance never appears.

    A NAMED HOST is emitted when one was verified free, with the node_type
    request commented beneath it. The trade-off is real and stated in the
    output rather than hidden: a named host is exactly the machine that was
    checked, and it fails outright if someone takes it between the check and
    the submit, where a type request would have been satisfied by any of its
    siblings.

    lease.get_node_reservation is NEVER emitted. It is deprecated and broken
    in python-chi 1.2.10 - _reservation_matching expects a lease dict while
    get_lease returns a Lease object, so it raises AttributeError. It appears
    throughout the corpus (A9, A55, A61, A63, A77), which means the artifacts
    teach an idiom that no longer runs.
    """
    name = _safe_name(rec)
    site = rec.site or "CHI@UC"
    image = rec.image or "CC-Ubuntu24.04"

    if rec.device_name:
        reservation = (
            f'my_lease.add_node_reservation(amount={rec.count}, '
            f'node_name="{rec.device_name}")\n'
            f'# Race-safe alternative: ask for the TYPE instead of this exact\n'
            f'# host. The named host above is the one verified free just now,\n'
            f'# and the reservation fails if someone else takes it first; the\n'
            f'# line below would be satisfied by any free {rec.machine_type}.\n'
            f'# my_lease.add_node_reservation(amount={rec.count}, '
            f'node_type="{rec.machine_type}")'
        )
    else:
        reservation = (
            f'my_lease.add_node_reservation(amount={rec.count}, '
            f'node_type="{rec.machine_type}")'
        )

    header = f"# grounded_by = {rec.grounded_by}  produced_by = {rec.produced_by}"
    if rec.selection_rung:
        header += f"\n# selection_rung = {rec.selection_rung}"
        if rec.wait_hours:
            header += (f"  (nothing free now; this frees up in about "
                       f"{rec.wait_hours:.1f}h, so the submit below will "
                       f"queue until then)")

    return f'''\
# --- chi-edge-advisor generated lease spec (baremetal) ---
{header}
from datetime import timedelta

import chi
from chi import lease, server

chi.use_site("{site}")

# 1) Lease with a NODE reservation. Bare metal reserves whole machines:
#    add_node_reservation, not add_device_reservation.
my_lease = lease.Lease("{name}-lease", duration=timedelta(hours={rec.duration_hours}))
{reservation}
my_lease.submit(idempotent=True)

# 2) Server. reservation_id must be the RESERVATION id taken from the lease,
#    not the lease id - the call accepts both and only one of them boots.
my_server = server.Server(
    name="{name}-node",
    reservation_id=my_lease.node_reservations[0]["id"],
    image_name="{image}",
)
my_server.submit(idempotent=True)

# my_server.associate_floating_ip()          # if public network access needed
# my_server.delete(); my_lease.delete()      # cleanup when done
'''


def _render_kvm(rec: Recommendation) -> str:
    """KVM@TACC. Reserve a flavor, then launch ON the reserved flavor.

    The grammar this replaces could not run. It emitted
    add_flavor_reservation(amount=..., flavor_name=...), and there is no
    flavor_name kwarg: the real signature in python-chi 1.2.10 is
    add_flavor_reservation(id=None, name=None, amount=1). It then wired the
    server with reservation_id, which is the bare-metal spelling.

    The form below is taken from benchmark golds CB03/CB04/CB05/CB16/CB30 and
    corpus artifacts A30/A57/A94, all of which execute.

    Launching with a LITERAL flavor name is the trap here, and it is a quiet
    one: KVM will happily hand you an on-demand instance, so nothing errors,
    the machine boots, and the reservation you are paying for sits unused for
    the life of the lease. flavor_name must come from the lease.
    """
    name = _safe_name(rec)
    site = rec.site or "KVM@TACC"
    image = rec.image or "CC-Ubuntu24.04"
    header = f"# grounded_by = {rec.grounded_by}  produced_by = {rec.produced_by}"
    if rec.selection_rung:
        header += f"\n# selection_rung = {rec.selection_rung}"

    return f'''\
# --- chi-edge-advisor generated lease spec (KVM) ---
{header}
from datetime import timedelta

import chi
from chi import lease, server

chi.use_site("{site}")

# 1) Lease with a FLAVOR reservation. KVM reserves capacity of a flavor, not
#    a named host, so there is no node_type and no device here.
my_lease = lease.Lease("{name}-lease", duration=timedelta(hours={rec.duration_hours}))
my_lease.add_flavor_reservation(
    id=chi.server.get_flavor_id("{rec.machine_type}"), amount={rec.count}
)
my_lease.submit(idempotent=True)

# 2) Virtual machine, launched ON the reserved flavor. Naming the flavor
#    literally here would boot an on-demand instance instead and leave the
#    reservation unused - it works, which is what makes it dangerous.
my_server = server.Server(
    "{name}-vm",
    image_name="{image}",
    flavor_name=my_lease.get_reserved_flavors()[0].name,
)
my_server.submit(idempotent=True)

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


#: Never emitted. Deprecated AND broken in python-chi 1.2.10: its
#: _reservation_matching expects a lease dict while get_lease returns a Lease
#: object, so it raises AttributeError. The corpus teaches it anyway.
BROKEN_IDIOMS = ("get_node_reservation",)


def _audit_source(code: str, family: str) -> List[str]:
    """Parse the rendered spec and confirm the wiring, without running it."""
    import ast

    out: List[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"FAIL rendered spec does not parse: {exc}"]

    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    kwargs = {k.arg for n in ast.walk(tree) if isinstance(n, ast.Call)
              for k in n.keywords if k.arg}

    for bad in BROKEN_IDIOMS:
        if bad in called:
            out.append(f"FAIL emits {bad}(), which raises AttributeError in "
                       "python-chi 1.2.10")

    if family == "baremetal":
        if "add_node_reservation" not in called:
            out.append("FAIL no add_node_reservation")
        if not ({"node_type", "node_name"} & kwargs):
            out.append("FAIL node reservation names neither a type nor a host")
        if "reservation_id" not in kwargs:
            out.append("FAIL server call has no reservation_id")
        elif "node_reservations" not in code:
            out.append("FAIL reservation_id is not derived from the lease "
                       "(passing the lease id here is the documented trap)")
        else:
            out.append("node reservation wired from the lease")
    else:
        if "add_flavor_reservation" not in called:
            out.append("FAIL no add_flavor_reservation")
        if "flavor_name" in kwargs and "get_reserved_flavors" not in called:
            out.append("FAIL flavor named literally rather than taken from "
                       "get_reserved_flavors() - the instance boots on demand "
                       "and the reservation goes unused")
        elif "get_reserved_flavors" in called:
            out.append("flavor wired from the lease's reserved flavors")
        else:
            out.append("FAIL server call does not name a reserved flavor")
    return out


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

    # The non-edge grammars are validated now, so they get checked rather than
    # excused. Both are verified against things that actually ran: the
    # bare-metal form submitted live on CHI@TACC, the KVM form is carried by
    # benchmark golds CB03/CB04/CB05/CB16/CB30 which all execute.
    #
    # Checked by parsing the rendered source instead of building objects,
    # because the KVM form calls chi.server.get_flavor_id(), which needs the
    # network. A dry check that reaches the network is not a dry check.
    if rec.api_family in {"baremetal", "kvm"}:
        details.extend(_audit_source(render_spec(rec), rec.api_family))
        return DryCheckResult(passed=not any(d.startswith("FAIL") for d in details),
                              mode="ast", details=details)

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
