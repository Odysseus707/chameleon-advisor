"""Normalized availability model + backend interface + config-driven factory."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import List, Optional

from ..config import settings


@dataclass
class DeviceAvailability:
    """One normalized view of a CHI@Edge device's identity + reservation state.

    Every backend maps its native representation onto this single dataclass so
    the rest of the pipeline never sees backend-specific shapes.

    Fields describing *live* state (`free_now`, `reserved_until`,
    `next_free_window`) may be ``None`` when the backend only knows static
    inventory. Consumers must treat ``free_now is None`` as "unknown", not
    "free".
    """

    device_uid: str
    machine_type: str
    device_profile: Optional[str] = None
    site: str = "CHI@Edge"
    architecture: Optional[str] = None
    gpu: bool = False
    peripherals: List[str] = field(default_factory=list)

    # Live reservation state (None => backend does not know).
    free_now: Optional[bool] = None
    reserved_until: Optional[str] = None  # ISO8601 timestamp
    next_free_window: Optional[str] = None  # ISO8601 timestamp or human range

    # Bookkeeping: which backend produced this record, and whether the live
    # fields are authoritative or merely inferred/static.
    source: str = "unknown"
    live_state_known: bool = False

    def is_free_in_window(self, *, unknown_ok: bool = False) -> Optional[bool]:
        """Convenience: is the device free right now?

        Returns True/False when known; None when unknown. When
        ``unknown_ok`` is True, unknown is treated as free (optimistic).
        """
        if self.free_now is None:
            return True if unknown_ok else None
        return self.free_now


class AvailabilityBackend(abc.ABC):
    """Common interface both backends implement."""

    #: short identifier used in logs / provenance
    name: str = "abstract"

    #: does this backend claim to report live reservation state?
    reports_live_state: bool = False

    @abc.abstractmethod
    def list_devices(
        self, machine_type: Optional[str] = None
    ) -> List[DeviceAvailability]:
        """Return normalized availability for CHI@Edge devices.

        When ``machine_type`` is given, restrict to that device type.
        """

    @abc.abstractmethod
    def get_device(self, device_uid: str) -> Optional[DeviceAvailability]:
        """Return normalized availability for a single device, or None."""

    def healthcheck(self) -> dict:
        """Lightweight reachability check. Override for richer diagnostics."""
        return {"backend": self.name, "reachable": True}


def get_backend(name: Optional[str] = None) -> AvailabilityBackend:
    """Factory: build the configured backend.

    ``name`` overrides config; otherwise `settings.availability_backend` wins.
    Importing backend implementations lazily keeps python-chi optional for the
    reference-API-only path.
    """
    chosen = (name or settings.availability_backend or "reference_api").lower()

    if chosen in {"reference_api", "reference", "refapi"}:
        from .reference_api import ReferenceApiBackend

        return ReferenceApiBackend()
    if chosen in {"blazar", "python-chi", "chi"}:
        from .blazar import BlazarBackend

        return BlazarBackend()

    raise ValueError(
        f"Unknown availability backend {chosen!r}; "
        "expected 'reference_api' or 'blazar'."
    )
