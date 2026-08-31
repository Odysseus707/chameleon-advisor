"""Regenerate advisor_room_render_golden.json.

Run this ONLY to re-baseline deliberately, never to make a failing test pass:

    LLM_PROVIDER=none python tests/data/_capture_golden_reference.py

The golden freezes advisor_room._render output for a spread of Recommendation
shapes, captured at commit 231e7ba (the advisor-integration checkpoint) before
reservation support was added. _render, _render_code, _device_line and
_further_reading are exactly the surface the reservation work modifies, so a
byte-identical assertion over these cases is what proves the disconnected path
- the one the benchmark drives - did not move.

advise() is deliberately not captured: it needs the bge embedder, the artifact
FAISS store and a live reference-API call, none of which are deterministic
enough to freeze. The functions below are pure.
"""
import json
import sys
from pathlib import Path

# tests/data/ -> tests/ -> chi-edge-advisor/ -> workspace root
WS = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WS / "RAG-docs-chameleon"))

import advisor_room  # noqa: E402
from advisor.availability.base import DeviceAvailability  # noqa: E402
from advisor.reason.schema import Recommendation  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "advisor_room_render_golden.json"


def dev(uid, mtype, free_now=None, hours=None, until=None):
    return DeviceAvailability(
        device_uid=uid,
        machine_type=mtype,
        site="CHI@Edge",
        free_now=free_now,
        available_hours=hours,
        reserved_until=until,
        source="fixture",
        live_state_known=free_now is not None,
    )


# One availability fixture, shared, covering every _device_line branch:
# known window / free-but-nothing-queued / reserved / live state unknown.
AVAIL = [
    dev("iot-rpi4-01", "raspberrypi4-64", free_now=True, hours=12.5),
    dev("iot-rpi4-02", "raspberrypi4-64", free_now=True),
    dev("iot-rpi4-03", "raspberrypi4-64", free_now=False,
        until="2026-09-01T18:00:00+00:00"),
    dev("iot-jetson-01", "jetson-nano", free_now=None),
]


def cases():
    return {
        # plainest possible: no device_name, profiles, ports or runtime
        "minimal": (Recommendation(
            machine_type="raspberrypi4-64", count=1, duration_hours=3,
            architecture="aarch64", image="python:3.11-slim",
            reasoning="Baseline container workload; no peripherals requested.",
            grounded_by=["serve-edge-chi"], produced_by="heuristic",
        ), AVAIL),

        # named device, free, known window, plus profiles and ports
        "named_free_window": (Recommendation(
            machine_type="raspberrypi4-64", count=2, duration_hours=6,
            architecture="aarch64", image="chameleon/picamera:latest",
            reasoning="Pi Camera capture needs the camera device profile.",
            device_name="iot-rpi4-01", device_profiles=["pi-camera-v3"],
            exposed_ports=[8080], platform_version=2,
            grounded_by=["serve-edge-chi"], produced_by="heuristic",
        ), AVAIL),

        # free, but nothing booked behind it (available_hours is None)
        "named_free_noqueue": (Recommendation(
            machine_type="raspberrypi4-64", count=1, duration_hours=2,
            architecture="aarch64", image="python:3.11-slim",
            reasoning="Short smoke test.",
            device_name="iot-rpi4-02",
            grounded_by=["serve-edge-chi"], produced_by="heuristic",
        ), AVAIL),

        # reserved: must say do not reserve this one
        "named_busy": (Recommendation(
            machine_type="raspberrypi4-64", count=1, duration_hours=4,
            architecture="aarch64", image="python:3.11-slim",
            reasoning="Requested a specific busy device.",
            device_name="iot-rpi4-03",
            grounded_by=["serve-edge-chi"], produced_by="heuristic",
        ), AVAIL),

        # named device absent from the snapshot entirely
        "named_absent": (Recommendation(
            machine_type="raspberrypi4-64", count=1, duration_hours=4,
            architecture="aarch64", image="python:3.11-slim",
            reasoning="Device id not present in the availability snapshot.",
            device_name="iot-rpi4-99",
            grounded_by=["serve-edge-chi"], produced_by="heuristic",
        ), AVAIL),

        # GPU/Jetson: runtime=nvidia, gpu=True, live state unknown
        "jetson_gpu": (Recommendation(
            machine_type="jetson-nano", count=1, duration_hours=8,
            architecture="aarch64", image="nvcr.io/nvidia/l4t-base:r32.7.1",
            reasoning="On-device inference needs the nvidia runtime.",
            device_name="iot-jetson-01", runtime="nvidia", gpu=True,
            device_profiles=["nvidia-gpu"], exposed_ports=[5000, 8888],
            grounded_by=["serve-edge-chi"], produced_by="heuristic",
        ), AVAIL),

        # availability lookup failed: advisor must still render
        "no_availability": (Recommendation(
            machine_type="raspberrypi4-64", count=1, duration_hours=3,
            architecture="aarch64", image="python:3.11-slim",
            reasoning="Availability lookup failed; advisor still renders.",
            device_name="iot-rpi4-01",
            grounded_by=[], produced_by="heuristic",
        ), []),

        # multi-device short lease, non-heuristic producer
        "multi_device": (Recommendation(
            machine_type="raspberrypi4-64", count=3, duration_hours=1,
            architecture="aarch64", image="python:3.11-slim",
            reasoning="Multi-device short lease.",
            grounded_by=["serve-edge-chi"], produced_by="tejas",
        ), AVAIL),
    }


def render_all():
    return {name: advisor_room._render(rec, avail)
            for name, (rec, avail) in cases().items()}


if __name__ == "__main__":
    GOLDEN.write_text(json.dumps(render_all(), indent=2) + "\n")
    print("wrote %s (%d cases)" % (GOLDEN, len(cases())))
