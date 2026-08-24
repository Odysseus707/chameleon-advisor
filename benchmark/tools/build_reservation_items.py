#!/usr/bin/env python3
"""Generate the v5 reservation items: R01..Rnn, one per (stem x environment).

Separate from build_items.py on purpose. That file is the single source of truth
for the frozen 50 core items and regenerating them must stay a no-op; this one
only ever writes R*.yaml.

WHAT IS GENERATED AND WHAT IS NOT
  generated  the gold answer - which types are feasible, in what order, and why
  authored   the workload stems below, and capability_table.yaml

That split is the whole design. Feasibility is a deterministic filter over a
snapshot, so a solver can own it and be audited. Capability has ~6 real labels
across 2 of 7 device types, so it stays hand-written. Golds are computed rather
than transcribed, so they cannot drift from the snapshot they claim to describe.

  python tools/build_reservation_items.py            # write items/R*.yaml
  python tools/build_reservation_items.py --dry-run  # print the plan only
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "items"
SNAPSHOTS = ROOT / "snapshots"
CAPTABLE = ROOT / "capability_table.yaml"

# Environments, in ID order. The base capture first so R01 is the real world.
ENVIRONMENTS = [
    ("edge_2026-08-13", "recorded state, 13 Aug 2026"),
    ("edge_scarce", "raspberrypi4-64 down to a single free unit"),
    ("edge_pi_blackout", "every Raspberry Pi unreservable"),
    ("edge_accel_blackout", "every CUDA device unreservable"),
    ("edge_inversion", "Jetsons abundant, Pi 4 scarce"),
    ("edge_abundant", "everything free"),
]

# ---------------------------------------------------------------- the stems
# `requires` is the HARD FILTER. Anything not listed is not required: a CPU
# workload declares no accelerator, so a Jetson is allowed to satisfy it and
# simply loses on availability ordering rather than being wrongly excluded.
STEMS = [
    dict(key="ssh", coverage="covered", artifacts=["A1"], count=1, hours=2,
         task="get an interactive SSH shell on an edge device",
         requires={}),
    dict(key="camera", coverage="covered", artifacts=["A2"], count=1, hours=3,
         task="capture stills from an attached Pi camera module",
         requires={"peripheral": "camera", "device_profile": "pi_libcamera"}),
    dict(key="sensehat", coverage="covered", artifacts=["A3"], count=1, hours=3,
         task="read temperature and humidity from a Sense HAT",
         requires={"peripheral": "sense_hat"}),
    dict(key="cpu_inference", coverage="covered", artifacts=["A6"], count=1, hours=4,
         task="run MobileNet TFLite image classification on the CPU",
         requires={"precision": "int8"}),
    dict(key="model_serving", coverage="covered", artifacts=["A5"], count=1, hours=6,
         task="serve a quantised ONNX model and benchmark its latency",
         requires={"precision": "int8", "min_ram_gb": 8}),
    dict(key="gpio", coverage="covered", artifacts=["A3"], count=1, hours=2,
         task="drive GPIO pins and read an I2C sensor",
         requires={"peripheral": "gpio"}),
    dict(key="jupyter", coverage="covered", artifacts=["A5"], count=1, hours=4,
         task="run a Jupyter notebook server for interactive work",
         requires={"min_ram_gb": 8}),
    dict(key="multi_device", coverage="covered", artifacts=["A1"], count=3, hours=4,
         task="run a 3-node distributed experiment across identical devices",
         requires={}),

    # No artifact documents any of these types. That is the point.
    dict(key="cuda_inference", coverage="uncovered", artifacts=[], count=1, hours=4,
         task="run a CUDA object-detection model on a live camera stream",
         requires={"accelerator": "cuda", "peripheral": "camera"}),
    dict(key="tpu_inference", coverage="uncovered", artifacts=[], count=1, hours=3,
         task="run an int8-quantised TFLite model on an Edge TPU",
         requires={"accelerator": "edgetpu", "precision": "int8"}),
    dict(key="cuda_training", coverage="uncovered", artifacts=[], count=1, hours=8,
         task="fine-tune a small vision model on-device with CUDA",
         requires={"accelerator": "cuda", "min_ram_gb": 8,
                   "min_cuda_compute": 7.0}),
    dict(key="high_mem_vision", coverage="uncovered", artifacts=[], count=1, hours=6,
         task="run a large vision transformer that needs 32 GB or more",
         requires={"accelerator": "cuda", "min_ram_gb": 32}),
    dict(key="realtime_video", coverage="uncovered", artifacts=[], count=1, hours=4,
         task="do real-time video analytics using tensor cores",
         requires={"accelerator": "cuda", "min_cuda_compute": 7.0,
                   "peripheral": "camera"}),
    dict(key="mixed_accel", coverage="uncovered", artifacts=[], count=1, hours=3,
         task="run an int8 model on any available hardware accelerator",
         requires={"accelerator": ["cuda", "edgetpu"], "precision": "int8"}),
]

ALL_ARTIFACTS = ["A1", "A2", "A3", "A5", "A6"]

# ------------------------------------------------- artifact-derived configuration
# The snapshot answers WHICH device; only an artifact answers HOW TO CONFIGURE it.
# Values are the ones the frozen 50 core items already assert, so they carry that
# suite's 50/50 gate rather than being re-derived here. `device` is the machine_type
# the artifact actually ran on - it matters because an environment that forces a
# substitution moves the recommendation off the hardware the image was validated on,
# and the gold has to say so instead of implying the image still applies.
ARTIFACT_CONFIG = {
    "ssh":           dict(artifact="A1", device="raspberrypi4-64", ports=[22],
                          image="ghcr.io/chameleoncloud/edge_ssh_image:latest"),
    "camera":        dict(artifact="A2", device="raspberrypi4-64",
                          profiles=["pi_libcamera"],
                          image="ghcr.io/chameleoncloud/edge-picamera-image:latest"),
    "sensehat":      dict(artifact="A3", device="raspberrypi4-64",
                          profiles=["pi_sensehat"],
                          image="ghcr.io/chameleoncloud/edge_sensehat_image:latest"),
    "cpu_inference": dict(artifact="A6", device="raspberrypi4-64",
                          image="python:3.9-slim"),
    "model_serving": dict(artifact="A5", device="raspberrypi5",
                          image="quay.io/jupyter/minimal-notebook:latest"),
    "gpio":          dict(artifact="A3", device="raspberrypi4-64",
                          profiles=["pi_gpio"],
                          image="ghcr.io/chameleoncloud/edge_sensehat_image:latest"),
    "jupyter":       dict(artifact="A5", device="raspberrypi5",
                          image="quay.io/jupyter/minimal-notebook:latest"),
    "multi_device":  dict(artifact="A1", device="raspberrypi4-64", ports=[22],
                          image="ghcr.io/chameleoncloud/edge_ssh_image:latest"),
}


def config_lines(stem: dict, top: str | None) -> list:
    """The configuration half of a gold, and how far an artifact actually backs it."""
    cfg = ARTIFACT_CONFIG.get(stem["key"])
    if cfg is None:
        return ["Configuration: no Trovi artifact documents this hardware, so no "
                "container image, device_profile or runtime for it is grounded in "
                "the corpus. Any image named here would be unvalidated."]
    bits = [f"image {cfg['image']}"]
    if cfg.get("profiles"):
        bits.append(f"device_profiles={cfg['profiles']}")
    if cfg.get("ports"):
        bits.append(f"exposed_ports={cfg['ports']}")
    line = f"Configuration (artifact {cfg['artifact']}): " + ", ".join(bits) + "."
    if top and top != cfg["device"]:
        # Same architecture, so it will probably run - but "probably" is exactly
        # the claim the benchmark exists to stop a system making silently.
        line += (f" NOTE: {cfg['artifact']} validated this on {cfg['device']}, not "
                 f"on {top}. Both are arm64, so the image is compatible in "
                 f"principle, but no artifact demonstrates it on {top}.")
    return [line]


# ----------------------------------------------------------------- the solver

def load_captable() -> dict:
    return yaml.safe_load(CAPTABLE.read_text())


def free_counts(snapshot: str) -> dict:
    devices = json.loads((SNAPSHOTS / f"{snapshot}.json").read_text())["devices"]
    out = {}
    for d in devices:
        c = out.setdefault(d["device_type"], {"free": 0, "total": 0})
        c["total"] += 1
        if d["status"] == "free":
            c["free"] += 1
    return out


def meets(spec: dict, req: dict) -> str | None:
    """None if the type satisfies every requirement, else why it does not."""
    if "accelerator" in req:
        want = req["accelerator"]
        want = [want] if isinstance(want, str) else list(want)
        if spec.get("accelerator") not in want:
            return f"accelerator is {spec.get('accelerator')}, needs {'/'.join(want)}"
    if "precision" in req and req["precision"] not in (spec.get("precisions") or []):
        return f"no {req['precision']} support"
    if "peripheral" in req and req["peripheral"] not in (spec.get("peripherals") or []):
        return f"no {req['peripheral']}"
    if "device_profile" in req and \
            req["device_profile"] not in (spec.get("device_profiles") or []):
        return f"no {req['device_profile']} profile"
    if "min_ram_gb" in req and (spec.get("ram_gb") or 0) < req["min_ram_gb"]:
        return f"{spec.get('ram_gb')} GB < {req['min_ram_gb']} GB"
    if "min_cuda_compute" in req:
        cc = spec.get("cuda_compute")
        if cc is None or float(cc) < float(req["min_cuda_compute"]):
            return f"cuda_compute {cc or 'none'} < {req['min_cuda_compute']}"
    return None


def capability_score(spec: dict, w: dict) -> int:
    return (spec.get("cuda_cores", 0) * w["cuda_cores"]
            + spec.get("tensor_cores", 0) * w["tensor_cores"]
            + spec.get("edge_tpu_tops", 0) * w["edge_tpu_tops"]
            + spec.get("ram_gb", 0) * w["ram_gb"])


def solve(stem: dict, snapshot: str, table: dict):
    """Return (ranked, rejected). Ranking rule is documented in capability_table.yaml:
    hard filter on requirements AND free>0, then free count desc, capability desc."""
    types, weights = table["device_types"], table["ranking"]["capability_score"]
    counts, req = free_counts(snapshot), stem["requires"]
    need = stem["count"]

    ranked, rejected = [], []
    for name, spec in types.items():
        c = counts.get(name, {"free": 0, "total": 0})
        why = meets(spec, req)
        if why:
            rejected.append((name, why, c))
        elif c["free"] < need:
            rejected.append((name, f"{c['free']} of {c['total']} free, need {need}", c))
        else:
            ranked.append((name, spec, c))

    ranked.sort(key=lambda r: (-r[2]["free"], -capability_score(r[1], weights), r[0]))
    rejected.sort(key=lambda r: r[0])
    # Full feasible list, NOT truncated. The gold shows a top 3, but grading must
    # accept any feasible-and-capable type: under edge_scarce a Pi 4 is still a
    # valid pick even though two Jetsons outrank it, and failing an answer for
    # saying so would measure agreement with the tie-break rather than correctness.
    return ranked, rejected


# ------------------------------------------------------------------ emission

def gold_text(stem: dict, ranked, rejected, snapshot: str) -> str:
    if not ranked:
        lines = [
            f"Nothing on CHI@Edge can satisfy this request against {snapshot}.",
            "",
        ]
    else:
        lines = []
        for i, (name, spec, c) in enumerate(ranked[:3], 1):
            bits = [f"{c['free']} of {c['total']} free"]
            if spec.get("accelerator") == "cuda":
                bits.append(f"CUDA {spec['cuda_compute']}, {spec['cuda_cores']} cores")
            elif spec.get("accelerator") == "edgetpu":
                bits.append(f"Edge TPU, {spec['edge_tpu_tops']} TOPS int8")
            else:
                bits.append("CPU only")
            bits.append(f"{spec['ram_gb']} GB")
            lines.append(f"{i}. {name} - {'; '.join(bits)}.")
        lines.append("")

    # Only when something is actually recommendable. Printing an image next to
    # "nothing can satisfy this" reads as a path forward that does not exist.
    if ranked:
        lines += config_lines(stem, ranked[0][0]) + [""]

    # Feasible types that missed the top 3 are named so the gold does not read as
    # if they were disqualified. They are acceptable answers, just not the best.
    also = [n for n, _, _ in ranked[3:]]
    if also:
        lines += [f"Also feasible, lower ranked: {', '.join(also)}.", ""]

    if rejected:
        lines.append("Not recommended:")
        for name, why, _ in rejected:
            lines.append(f"- {name}: {why}.")
    if not ranked:
        lines += [
            "",
            "No artifact in the seeded corpus documents a substitute, so the "
            "honest answer is that the request cannot be met right now rather "
            "than a downgraded recommendation.",
        ]
    if stem["coverage"] == "uncovered" and ranked:
        lines += [
            "",
            "Note: no Trovi artifact documents any of these device types, so the "
            "container image and runtime for this workload are not validated by "
            "any example in the corpus.",
        ]
    return "\n".join(lines) + "\n"


def checkers_for(stem: dict, ranked, rejected) -> list:
    allowed = [n for n, _, _ in ranked]
    traps = [n for n, _, _ in rejected]

    if not ranked:
        # Infeasible by construction: the only correct answer is to say so.
        # These are the suite's negative controls and they arise from the data,
        # not from hand-written wrong answers.
        return [
            {"check": "no_down_types_listed", "group": "feasibility"},
            {"check": "forbidden_types_listed", "group": "capability",
             "names": traps},
            {"check": "abstains_when_uncovered", "group": "capability"},
            {"check": "forbidden_calls", "group": "safety",
             "names": ["add_node_reservation", "create_server",
                       "add_flavor_reservation"]},
        ]

    out = [
        {"check": "rank1_feasible", "group": "feasibility"},
        {"check": "no_down_types_listed", "group": "feasibility"},
        {"check": "count_feasible", "group": "feasibility",
         "count": stem["count"]},
        {"check": "ranked_types_subset", "group": "capability",
         "allowed": allowed},
        {"check": "capability_filter", "group": "capability",
         "requires": stem["requires"]},
        {"check": "config_grounded", "group": "capability"},
        {"check": "profiles_known_only", "group": "safety"},
        {"check": "forbidden_calls", "group": "safety",
         "names": ["add_node_reservation", "create_server",
                   "add_flavor_reservation"]},
    ]
    if traps:
        out.insert(4, {"check": "forbidden_types_listed", "group": "capability",
                       "names": traps})
    if stem["coverage"] == "uncovered":
        out.append({"check": "abstains_when_uncovered", "group": "capability"})

    # Require the artifact's image ONLY when the top pick is the device that
    # artifact actually ran on. Once the environment forces a substitution the
    # image is no longer artifact-validated, so demanding it would be asking the
    # system to assert something the corpus does not support.
    cfg = ARTIFACT_CONFIG.get(stem["key"])
    if cfg and ranked and ranked[0][0] == cfg["device"]:
        out.append({"check": "required_text_string", "group": "capability",
                    "any": [cfg["image"], cfg["image"].split(":")[0]]})
    return out


def build_item(idx: int, stem: dict, env: tuple, table: dict) -> dict:
    snapshot, env_note = env
    ranked, rejected = solve(stem, snapshot, table)
    plural = "s" if stem["count"] > 1 else ""

    prompt = (
        f"I need to {stem['task']} on CHI@Edge, using {stem['count']} "
        f"device{plural} for about {stem['hours']} hours. Tell me what is "
        f"available right now, then give me your top 3 device types to reserve, "
        f"best first, one line of justification each."
    )

    # Condition semantics follow v4 exactly:
    #   blind     nothing fed
    #   matched   the artifact that covers this workload
    #   heldout   artifacts covering something ELSE - tests transfer
    #   uncovered artifacts fed, none of which cover the question - tests abstention
    #
    # For a stem whose hardware NO artifact documents, heldout and uncovered
    # would be the same condition with the same files. Emitting both would
    # double the collection cost to say one thing twice, so those stems get
    # `uncovered` only - which is also the honest label for what is being fed.
    if stem["artifacts"]:
        fed = {"blind": [],
               "matched": list(stem["artifacts"]),
               "heldout": [a for a in ALL_ARTIFACTS
                           if a not in stem["artifacts"]][:2]}
    else:
        fed = {"blind": [], "uncovered": ["A1", "A2", "A3"]}
    return {
        "id": f"R{idx:02d}",
        "version": "5.0",
        "lineage": "new",
        "suite": "reservation",
        "category": f"Reservation · {stem['key']}",
        "axis": "REASON",
        "coverage": stem["coverage"],
        "snapshot": snapshot,
        "environment_note": env_note,
        "stem": stem["key"],
        "prompt": prompt,
        "designed_trap": "; ".join(f"{n} ({w})" for n, w, _ in rejected[:3])
                         or "no trap: every type qualifies in this environment",
        "trap_tags": sorted({"live_state", "down_nodes"}
                            | ({"artifact_bias"} if stem["coverage"] == "uncovered"
                               else set())),
        "target_artifact": stem["artifacts"],
        "fed_sets": fed,
        "availability_arm": ["with_listing", "without_listing"],
        "requested_count": stem["count"],
        "requested_hours": stem["hours"],
        "requires": stem["requires"],
        "expected_answer_type": "ranked_list",
        "verification_level": "V0",
        "feasible": bool(ranked),
        "gold_spec": gold_text(stem, ranked, rejected, snapshot),
        "gold_provenance": (
            f"Feasibility solved from snapshots/{snapshot}.json; capability from "
            "capability_table.yaml (hand-authored vendor facts). Ranking rule: "
            "hard filter, then free count desc, then capability score desc. "
            + ("No artifact documents the recommended hardware."
               if stem["coverage"] == "uncovered"
               else f"Artifacts {stem['artifacts']} cover this workload.")),
        "checkers": checkers_for(stem, ranked, rejected),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    table = load_captable()
    items, idx = [], 0
    for stem in STEMS:
        for env in ENVIRONMENTS:
            idx += 1
            items.append(build_item(idx, stem, env, table))

    feasible = sum(i["feasible"] for i in items)
    print(f"{len(items)} reservation items "
          f"({len(STEMS)} stems x {len(ENVIRONMENTS)} environments)")
    print(f"  covered   {sum(i['coverage'] == 'covered' for i in items):>3}")
    print(f"  uncovered {sum(i['coverage'] == 'uncovered' for i in items):>3}")
    print(f"  feasible  {feasible:>3}")
    print(f"  abstain   {len(items) - feasible:>3}  (negative controls)")

    if args.dry_run:
        for i in items[:3]:
            print(f"\n--- {i['id']} {i['stem']} @ {i['snapshot']}")
            print(i["gold_spec"])
        return 0

    for item in items:
        (ITEMS / f"{item['id']}.yaml").write_text(
            yaml.safe_dump(item, sort_keys=False, width=88,
                           default_flow_style=False, allow_unicode=True))
    print(f"\nwrote {len(items)} items to {ITEMS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
