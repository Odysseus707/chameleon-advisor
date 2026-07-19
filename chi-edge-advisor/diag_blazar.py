"""One-shot Blazar device-read diagnostic.

Run this in the SAME shell where your Chameleon credentials are loaded
(the shell where `python -m advisor.cli ...` already authenticates):

    python diag_blazar.py

It isolates the live device read so we can see exactly what Blazar returns,
independent of the rest of the advisor pipeline.
"""
from __future__ import annotations

import chi
from chi.clients import blazar
from advisor.config import settings


def main() -> None:
    print(f"site         : {settings.chi_site_name}")
    print(f"project      : {settings.chi_project_name}")
    import os
    chi.use_site(settings.chi_site_name)
    # Skip project scope when using Application Credentials — scope is already
    # embedded in the credential; setting it again causes a 401.
    if settings.chi_project_name and os.environ.get("OS_AUTH_TYPE") != "v3applicationcredential":
        chi.set("project_name", settings.chi_project_name)

    cl = blazar()
    print("has .device  :", hasattr(cl, "device"))

    # 1) Raw Blazar device inventory (all registered edge devices).
    devices = cl.device.list()
    print(f"\nBlazar device.list()  -> {len(devices)} devices")
    for d in devices[:15]:
        print(
            "   uid={uid}  name={name}  type={dtype}  reservable={res}".format(
                uid=d.get("uid"),
                name=d.get("name"),
                dtype=d.get("device_type"),
                res=d.get("reservable"),
            )
        )

    # 2) Current allocations (what is reserved right now).
    try:
        allocs = cl.device.list_allocations()
        reserved = sum(len(a.get("reservations", [])) for a in allocs)
        print(f"\ndevice.list_allocations() -> {len(allocs)} rows, {reserved} reservations")
    except Exception as exc:  # noqa: BLE001
        print(f"\nlist_allocations failed: {type(exc).__name__}: {exc}")

    # 3) The exact call python-chi / our backend uses.
    from chi import hardware
    hw = hardware.get_devices()
    free = hardware.get_devices(filter_reserved=True)
    print(f"\nhardware.get_devices()               -> {len(hw)} devices")
    print(f"hardware.get_devices(filter_reserved) -> {len(free)} free now")

    # 4) Inspect the Device object fields so we can map them correctly.
    if hw:
        dev = hw[0]
        print(f"\nDevice object type : {type(dev)}")
        print("All attributes     :")
        for attr in sorted(vars(dev) if hasattr(dev, '__dict__') else []):
            print(f"  {attr} = {getattr(dev, attr, '?')!r}")
        # Also try the underlying dict if available
        if hasattr(dev, '_info') or hasattr(dev, 'to_dict'):
            raw = dev._info if hasattr(dev, '_info') else dev.to_dict()
            print("\nUnderlying _info dict keys:", list(raw.keys())[:30])
            for k,v in list(raw.items())[:20]:
                print(f"  {k} = {v!r}")


if __name__ == "__main__":
    main()
