"""Validator: check a Recommendation against known CHI@Edge traps.

Each check returns pass/fail with a human-readable detail. The report as a whole
passes only if every non-warning check passes. Checks are deliberately
conservative: when live availability is unknown, "is it free?" fails rather than
optimistically passing, because emitting a spec for a reserved device is a trap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..availability.base import DeviceAvailability
from ..inventory.catalog import DeviceType
from ..reason.schema import Recommendation


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class ValidationReport:
    checks: List[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "error")

    def add(self, name: str, passed: bool, detail: str, severity: str = "error") -> None:
        self.checks.append(CheckResult(name, passed, detail, severity))

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [c.__dict__ for c in self.checks],
        }


def validate_recommendation(
    rec: Recommendation,
    inventory: List[DeviceType],
    availability: Optional[List[DeviceAvailability]] = None,
) -> ValidationReport:
    availability = availability or []
    report = ValidationReport()
    inv = {dt.machine_type: dt for dt in inventory}
    dt = inv.get(rec.machine_type)

    # 1. machine_type exists in inventory --------------------------------
    report.add(
        "machine_type_exists",
        dt is not None,
        f"machine_type '{rec.machine_type}' "
        + ("found in inventory." if dt else "NOT in inventory."),
    )

    # 2. architecture match ----------------------------------------------
    if dt is None:
        report.add(
            "architecture_match", False,
            "cannot verify architecture: machine_type unknown.",
        )
    else:
        ok = rec.architecture == dt.architecture
        report.add(
            "architecture_match", ok,
            f"recommended arch '{rec.architecture}' vs inventory "
            f"'{dt.architecture}' for {rec.machine_type}.",
        )

    # 3. device_profile(s) exist -----------------------------------------
    if rec.device_profiles:
        if dt is None:
            report.add("device_profile_exists", False,
                       "machine_type unknown; cannot verify device_profiles.")
        else:
            unknown = [p for p in rec.device_profiles if p not in dt.device_profiles]
            report.add(
                "device_profile_exists", not unknown,
                f"unknown profiles {unknown} for {rec.machine_type}"
                if unknown else
                f"profiles {rec.device_profiles} valid for {rec.machine_type}.",
            )
    else:
        report.add("device_profile_exists", True,
                   "no device_profiles requested.", severity="warning")

    # 4. device actually free in the requested window --------------------
    of_type = [d for d in availability if d.machine_type == rec.machine_type]
    if rec.device_name:
        match = next((d for d in of_type if d.device_uid == rec.device_name), None)
        if match is None:
            report.add("device_free_in_window", False,
                       f"device '{rec.device_name}' not seen in availability data.")
        elif match.free_now is True:
            report.add("device_free_in_window", True,
                       f"device '{rec.device_name}' is free now.")
        elif match.free_now is False:
            report.add("device_free_in_window", False,
                       f"device '{rec.device_name}' is reserved "
                       f"(until {match.reserved_until}).")
        else:
            report.add("device_free_in_window", False,
                       f"device '{rec.device_name}' live state UNKNOWN "
                       "(reference API is static-only; use blazar backend).")
    else:
        free = [d for d in of_type if d.free_now is True]
        if not availability:
            report.add("device_free_in_window", False,
                       "no availability data; cannot confirm free devices "
                       "(use blazar backend for live state).")
        elif len(free) >= rec.count:
            report.add("device_free_in_window", True,
                       f"{len(free)} free {rec.machine_type} device(s) "
                       f">= requested count {rec.count}.")
        else:
            report.add("device_free_in_window", False,
                       f"only {len(free)} free {rec.machine_type} device(s) "
                       f"< requested count {rec.count}.")

    # 5. platform_version present ----------------------------------------
    report.add(
        "platform_version_present",
        isinstance(rec.platform_version, int) and rec.platform_version >= 1,
        f"platform_version={rec.platform_version}.",
    )

    # 6. runtime=nvidia for GPU workload on a Jetson ---------------------
    is_jetson = "jetson" in rec.machine_type.lower() or (dt is not None and dt.gpu)
    if rec.gpu and is_jetson:
        report.add(
            "gpu_runtime_nvidia",
            rec.runtime == "nvidia",
            f"GPU workload on {rec.machine_type} requires runtime='nvidia'; "
            f"got runtime={rec.runtime!r}.",
        )
    else:
        report.add("gpu_runtime_nvidia", True,
                   "not a Jetson GPU workload; runtime check N/A.",
                   severity="warning")

    return report
