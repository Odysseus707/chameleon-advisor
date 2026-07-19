"""Availability adapter: normalized live/near-live device state for CHI@Edge.

Two interchangeable backends sit behind `AvailabilityBackend`:
  - ReferenceApiBackend: static catalog from the reference API (+ opportunistic
    live-status probe).
  - BlazarBackend: authoritative live host/lease state via python-chi.

The backend is chosen by config (`AVAILABILITY_BACKEND`), never hardcoded at
call sites -- use `get_backend()`.
"""
from .base import (
    AvailabilityBackend,
    DeviceAvailability,
    get_backend,
)

__all__ = ["AvailabilityBackend", "DeviceAvailability", "get_backend"]
