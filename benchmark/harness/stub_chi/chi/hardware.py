import json
import os
from types import SimpleNamespace


def _load():
    with open(os.environ["CHI_SNAPSHOT"]) as f:
        snap = json.load(f)
    return snap["devices"]


def get_devices(filter_reserved=False, device_type=None):
    """Mirror python-chi hardware.get_devices for CHI@Edge.
    filter_reserved=True -> only devices free right now."""
    devs = []
    for d in _load():
        if device_type is not None and d["device_type"] != device_type:
            continue
        if filter_reserved and not d["free"]:
            continue
        devs.append(SimpleNamespace(
            device_name=d["device_name"],
            device_type=d["device_type"],
            reservable=d.get("reservable", True),
            uuid=d["uuid"],
            supported_device_profiles=d.get("supported_device_profiles", []),
            authorized_projects=set(d.get("authorized_projects", ["all"])),
            owning_project=d.get("owning_project", ""),
        ))
    return devs
