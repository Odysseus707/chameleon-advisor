"""BlazarBackend: authoritative live CHI@Edge state via python-chi.

Live reservation/availability state lives in Blazar (the portal Host Calendar
is a Blazar view). python-chi's `hardware.get_devices()` reads host/lease state
and supports `filter_reserved=True`, which is exactly the live signal the
reference API lacks.

python-chi requires credentials/site context to actually talk to Blazar, so
this backend is import-guarded: constructing it without python-chi installed
raises a clear error, and the reference-API path never imports it.
"""
from __future__ import annotations

from typing import List, Optional

from ..config import settings
from .base import AvailabilityBackend, DeviceAvailability


class BlazarBackend(AvailabilityBackend):
    name = "blazar"
    reports_live_state = True

    def __init__(self, site_name: Optional[str] = None):
        self.site_name = site_name or settings.chi_site_name
        try:
            import chi  # noqa: F401
            from chi import hardware  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "BlazarBackend requires python-chi. Install with "
                "`pip install python-chi` and configure Chameleon credentials, "
                "or select AVAILABILITY_BACKEND=reference_api."
            ) from exc
        self._chi = chi
        self._hardware = hardware
        self._configured = False

    def _ensure_site(self) -> None:
        if self._configured:
            return
        self._chi.use_site(self.site_name)
        # Application Credentials already carry the project scope; setting it
        # again causes Keystone to reject the auth with "cannot request a scope".
        import os
        if settings.chi_project_name and os.environ.get("OS_AUTH_TYPE") != "v3applicationcredential":
            self._chi.set("project_name", settings.chi_project_name)
        self._configured = True

    # Derive architecture and GPU flag from the device_type string since
    # python-chi Device objects don't expose separate arch/gpu attributes.
    _ARM64_TYPES = {"raspberrypi4-64", "raspberrypi3", "raspberrypi5"}
    _GPU_TYPES = {"jetson-nano", "jetson-xavier-nx", "jetson-agx-xavier",
                  "nvidia-jetson-agx-orin", "jetson-orin-nano"}

    @classmethod
    def _device_to_availability(cls, dev, free: bool) -> DeviceAvailability:
        machine_type = getattr(dev, "device_type", None) or "unknown"
        # supported_device_profiles is the real field; peripherals doesn't exist.
        profiles = list(getattr(dev, "supported_device_profiles", None) or [])
        mt_lower = machine_type.lower()
        if any(t in mt_lower for t in ("rpi", "raspberrypi")):
            arch = "arm64"
        elif any(t in mt_lower for t in ("jetson", "orin", "agx", "xavier", "nano")):
            arch = "arm64"
        else:
            arch = None
        gpu = machine_type in cls._GPU_TYPES or any(
            k in mt_lower for k in ("jetson", "orin", "agx", "xavier")
        )
        return DeviceAvailability(
            device_uid=getattr(dev, "device_name", None) or str(dev),
            machine_type=machine_type,
            architecture=arch,
            gpu=gpu,
            peripherals=profiles,
            free_now=free,
            reserved_until=getattr(dev, "reserved_until", None),
            next_free_window=getattr(dev, "next_free_window", None),
            source="blazar",
            live_state_known=True,
        )

    def list_devices(
        self, machine_type: Optional[str] = None
    ) -> List[DeviceAvailability]:
        self._ensure_site()
        kwargs = {}
        if machine_type:
            kwargs["device_type"] = machine_type
        # All devices of the type, and the free subset, to compute free_now.
        all_devs = self._hardware.get_devices(**kwargs)
        free_devs = self._hardware.get_devices(filter_reserved=True, **kwargs)
        free_names = {getattr(d, "device_name", None) for d in free_devs}
        out = []
        for dev in all_devs:
            name = getattr(dev, "device_name", None)
            out.append(self._device_to_availability(dev, free=name in free_names))
        return out

    def get_device(self, device_uid: str) -> Optional[DeviceAvailability]:
        for dev in self.list_devices():
            if dev.device_uid == device_uid:
                return dev
        return None

    def healthcheck(self) -> dict:
        try:
            self._ensure_site()
            return {"backend": self.name, "reachable": True, "site": self.site_name}
        except Exception as exc:  # noqa: BLE001
            return {"backend": self.name, "reachable": False, "error": str(exc)}
