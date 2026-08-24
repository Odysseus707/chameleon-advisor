"""Stub `chi` package for V1 snapshot execution (benchmark v4).

Implements only the read-side API needed by availability items, backed by the
JSON snapshot at $CHI_SNAPSHOT. Device fields mirror the real python-chi Device
object as verified in the chi-edge-advisor prototype notes (device_name,
device_type, reservable, uuid, supported_device_profiles, authorized_projects,
owning_project). Anything write-side raises to prevent accidental misuse.
"""

from . import hardware, context  # noqa: F401


def use_site(name):  # imperative-style site selection is a no-op here
    return None


def set(key, value):  # noqa: A001 - mirrors chi.set
    return None
