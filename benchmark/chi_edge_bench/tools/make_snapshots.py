#!/usr/bin/env python3
"""Build the benchmark v5 snapshot family from the recorded CHI@Edge capture.

The v4 snapshot was 10 invented devices with a `free` boolean. That cannot
express the dominant fact in the real data: 33 of 68 CHI@Edge devices are DOWN,
not busy, and two whole device types are 100% unreservable. So the schema gains
a three-valued `status`; `free` and `reservable` are kept and derived from it so
harness/stub_chi keeps working unchanged.

  status   free    reservable   meaning
  free     True    True         reservable right now
  busy     False   True         a lease covers now
  down     False   False        Blazar reports reservable=False

Perturbations exist because CHI@Edge has almost no contention (2 busy of 68), so
the real capture alone cannot test whether a system tracks state. Every variant
is a pure function of the base capture - no RNG, no hand editing - so the whole
family regenerates byte-identically.

  python tools/make_snapshots.py            # regenerate all, from the base
  python tools/make_snapshots.py --capture <probe.json>   # re-derive the base
  python tools/make_snapshots.py --check    # verify on-disk files match

Device capabilities are deliberately NOT written here. Blazar exposes none, and
mixing vendor facts into a recorded capture would make the capture untrustworthy.
They live in capability_table.yaml.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from chi_edge_bench.paths import snapshots_dir, workspace

SNAPSHOTS = snapshots_dir()
BASE = SNAPSHOTS / "edge_2026-08-13.json"

# The probe output this was recorded from. Gitignored (presentation_assets is
# generated), so the committed BASE is the fallback source for perturbations.
DEFAULT_CAPTURE = (workspace() / "captures"
                   / "fig2_probe_all_sites_2026-08-13.json")

SITE = "CHI@Edge"


def _status(node: dict) -> str:
    """Trust the probe's own classification; fall back to the raw fields."""
    s = node.get("status")
    if s in ("free", "busy", "down"):
        return s
    if not node.get("reservable", True):
        return "down"
    return "free" if node.get("immediately_available") else "busy"


def from_capture(capture_path: Path) -> dict:
    """Reshape the CHI@Edge slice of a probe capture into the snapshot schema."""
    raw = json.loads(capture_path.read_text())
    sites = [s for s in raw.get("sites", []) if s.get("site") == SITE]
    if not sites:
        raise SystemExit(f"no {SITE} slice in {capture_path}")
    nodes = sites[0]["nodes"]

    devices = []
    for n in sorted(nodes, key=lambda x: str(x.get("name") or "")):
        st = _status(n)
        devices.append({
            "device_name": n["name"],
            "device_type": n["node_type"],
            "status": st,
            "free": st == "free",
            "reservable": st != "down",
            "uuid": n["uid"],
            # Blazar exposes neither of these; empty is honest. Capabilities
            # come from capability_table.yaml, never from a recorded capture.
            "supported_device_profiles": [],
            "authorized_projects": ["all"],
            "owning_project": "chameleon",
        })

    return {
        "_meta": {
            "SYNTHETIC": False,
            "variant": "base",
            "note": ("Recorded CHI@Edge state via Blazar, reshaped from a "
                     "probe_availability.py capture. Real data."),
            "site": SITE,
            "recorded": raw.get("generated_utc"),
            "source_sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            "schema": ["device_name", "device_type", "status", "free",
                       "reservable", "uuid", "supported_device_profiles",
                       "authorized_projects", "owning_project"],
        },
        "devices": devices,
    }


# ------------------------------------------------------------------ variants
# Each takes the base device list and returns a modified copy. Deterministic:
# devices are already name-sorted, and selection is always "first N of a type".

def _set(devices, predicate, status):
    out = []
    for d in devices:
        d = dict(d)
        if predicate(d):
            d["status"] = status
            d["free"] = status == "free"
            d["reservable"] = status != "down"
        out.append(d)
    return out


def _keep_n_free(devices, device_type, n, otherwise="busy"):
    """Leave the first `n` free devices of a type free; move the rest."""
    seen = 0
    out = []
    for d in devices:
        d = dict(d)
        if d["device_type"] == device_type and d["status"] == "free":
            seen += 1
            if seen > n:
                d["status"] = otherwise
                d["free"] = False
                d["reservable"] = otherwise != "down"
        out.append(d)
    return out


def v_scarce(devices):
    """The abundant, well-documented type drops to a single free unit.

    Tests whether count requests are checked against real headroom rather than
    assumed. raspberrypi4-64 normally has 22 free.
    """
    return _keep_n_free(devices, "raspberrypi4-64", 1)


def v_pi_blackout(devices):
    """Every Pi is down. The only remaining hardware is uncovered by artifacts.

    The sharpest H0/H1 probe: a lookup system has nothing left to name.
    """
    return _set(devices, lambda d: d["device_type"].startswith("raspberrypi"),
                "down")


def v_accel_blackout(devices):
    """Every CUDA part is down. GPU workloads become genuinely infeasible.

    Correct behaviour is to say so, not to substitute a Pi or a Coral.
    """
    cuda = {"jetson-nano", "jetson-xavier-nx-devkit-emmc",
            "jetson-orin-nano-devkit-nvme", "jetson-agx-orin-devkit-64gb"}
    return _set(devices, lambda d: d["device_type"] in cuda, "down")


def v_inversion(devices):
    """The rare type becomes the abundant one and vice versa.

    A system that memorised "recommend the Pi" fails here while a system reading
    state follows the inversion.
    """
    out = _keep_n_free(devices, "raspberrypi4-64", 1)
    return _set(out, lambda d: d["device_type"].startswith("jetson"), "free")


def v_abundant(devices):
    """Everything reservable. Control: nothing is scarce, so feasibility checks
    should all pass and only capability separates systems."""
    return _set(devices, lambda d: True, "free")


VARIANTS = {
    "edge_scarce": (v_scarce, "raspberrypi4-64 down to 1 free unit"),
    "edge_pi_blackout": (v_pi_blackout, "all Raspberry Pi types unreservable"),
    "edge_accel_blackout": (v_accel_blackout, "all CUDA devices unreservable"),
    "edge_inversion": (v_inversion, "Jetsons abundant, Pi 4 scarce"),
    "edge_abundant": (v_abundant, "every device free; scarcity removed"),
}


def build_variant(base: dict, name: str) -> dict:
    fn, note = VARIANTS[name]
    meta = dict(base["_meta"])
    meta.update({
        "SYNTHETIC": True,
        "variant": name,
        "note": (f"DERIVED from {BASE.name} by tools/make_snapshots.py: {note}. "
                 "Counterfactual for state-sensitivity testing, not a recording."),
        "derived_from": BASE.name,
    })
    return {"_meta": meta, "devices": fn(base["devices"])}


def _render(snap: dict) -> str:
    return json.dumps(snap, indent=1, sort_keys=False) + "\n"


def summarise(name: str, snap: dict) -> str:
    from collections import Counter
    c = Counter(d["status"] for d in snap["devices"])
    return (f"  {name:22} {c['free']:>3} free  {c['busy']:>3} busy  "
            f"{c['down']:>3} down   {len(snap['devices']):>3} total")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capture", type=Path, default=None,
                    help="re-derive the base from a probe_availability.py JSON")
    ap.add_argument("--check", action="store_true",
                    help="verify on-disk snapshots match what this would write")
    args = ap.parse_args()

    SNAPSHOTS.mkdir(exist_ok=True)

    if args.capture or not BASE.is_file():
        cap = args.capture or DEFAULT_CAPTURE
        if not cap.is_file():
            raise SystemExit(
                f"no base snapshot at {BASE} and no capture at {cap}.\n"
                "Pass --capture <probe json> to derive the base.")
        base = from_capture(cap)
    else:
        base = json.loads(BASE.read_text())

    outputs = {BASE.name: base}
    for name in VARIANTS:
        outputs[f"{name}.json"] = build_variant(base, name)

    drift = []
    for fname, snap in outputs.items():
        path, text = SNAPSHOTS / fname, _render(snap)
        if args.check:
            if not path.is_file() or path.read_text() != text:
                drift.append(fname)
        else:
            path.write_text(text)
        print(summarise(fname[:-5], snap))

    if args.check:
        if drift:
            print(f"\nDRIFT: {drift} do not match regeneration", file=sys.stderr)
            return 1
        print("\nall snapshots match regeneration")
    else:
        print(f"\nwrote {len(outputs)} snapshots to {SNAPSHOTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
