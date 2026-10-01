#!/usr/bin/env python3
"""refill_capability_table: ram_gb and vcpus from the reference-API capture.

  python corpus_v2/tools/refill_capability_table.py            # report only
  python corpus_v2/tools/refill_capability_table.py --apply    # write the table

WHAT IT FIXES
Two problems in one column, both invisible until the reference API gave a second
opinion:

  MISSING     17 of 29 types carry ram_gb: null / vcpus: null, because Blazar
              reported memory_mb for only 102 of 345 TACC hosts. Under R4 a null
              FAILS every minimum, so those types are excluded from 12 items for
              lack of data rather than lack of capability.

  INCONSISTENT the 12 non-null rows do not share a unit. compute_haswell_ib,
              gpu_k80, gpu_m40 and gpu_p100 are all 2x Xeon E5-2670 v3 - the
              same silicon, 24 cores and 48 threads. The table says 24 for the
              first and 48 for the other three. Blazar's `vcpus` is whatever
              Ironic recorded per node, so the column was never "cores" or
              "threads"; it was both. Every threshold tested against it was
              therefore testing different quantities on different rows.

Refilling the WHOLE column from one source fixes the second problem, which a
null-fill alone would have left in place.

THE UNIT IS PHYSICAL CORES
Chosen over threads so that a stem written as `min_vcpus: 32` keeps the
difficulty it was authored with. cores = threads / smt_factor, and smt_factor is
2 on x86_64 and 1 on aarch64 - the Ampere Altra in compute_arm64 has no SMT, so
halving it would invent a machine half its size. This one conversion is the only
assumption in the refill and it is stated per row by `capability_source`.

WHY max() AND NOT min() FOR HOMOGENEOUS TYPES
The reference API is itself inconsistently populated: 4 of 24 compute_cascadelake
nodes report smt_size 32 where the other 20 report 64, all with the same Gold
6242 (16 cores x 2 sockets = 32 cores, 64 threads). The low records report cores
in a field the others fill with threads. Under-reporting only ever reports FEWER,
so for one machine the maximum is the true thread count - and it is checkable:
where the CPU model names its own core count ("EPYC 7352 24-Core Processor"),
cores_per_socket x smp_size must equal the derived vcpus. That cross-check runs
on every row and any mismatch is printed.

...AND max() WITHIN ONE TYPE IS NOT ENOUGH
Both gpu_h100 and gpu_pontevecchio are 2x Xeon Platinum 8468. h100's records say
192 threads; BOTH pontevecchio records say 96. A per-type maximum cannot see
that, and would have written pontevecchio down at half its cores - the same
silicon recorded as two different machines, which is the exact defect this tool
exists to remove. So threads are resolved per (cpu_model, sockets) ACROSS types:
the same CPU in the same socket count is the same machine wherever it appears,
and the highest thread count any type reports for it is the true one. Of the 13
(model, sockets) pairs in the fleet, 12 are unanimous across every type using
them; Platinum 8468 is the only disagreement, which is why this is a correction
and not a guess.

...EXCEPT WHERE THE TYPE IS TWO MACHINES
compute_gigaio is 6 Intel/256 GB nodes at CHI@TACC and 8 AMD/512 GB nodes at
CHI@UC. That is not under-reporting, it is one name over two machines, and a
scalar cannot describe it. There the MINIMUM is taken, because the only thing
the type guarantees is its weaker half, and a reservation that assumes 512 GB
gets 256 half the time. The two cases are told apart by cpu_models: one specific
model with a spread is a thin record, two specific models is heterogeneity.
A vendor-only string like "Intel Xeon" names no model and is not counted as one.

WHAT IT DOES NOT TOUCH
node_count and sites (Blazar's, and reconciled separately), every VENDOR field,
and the `ranking.capability_score` weights - which contain keys literally named
ram_gb and vcpus and must never be caught by this rewrite. Types absent from the
reference API keep their Blazar values and say so per row.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
WING = BENCH / "chameleon_bench"
TABLE = WING / "data" / "capability_table.yaml"
REF_DIR = WING / "data" / "reference_api"

#: Provenance kept by rows the reference API does not describe. The capture
#: these came from; not re-probed here.
BLAZAR_SOURCE = "blazar_2026-09-04"

#: Threads per physical core. aarch64 here is the Ampere Altra in compute_arm64,
#: which has no SMT at all.
SMT_FACTOR = {"x86_64": 2, "aarch64": 1}

_CORES_IN_MODEL = re.compile(r"(\d+)-Core")

#: VENDOR facts per SINGLE accelerator: (cuda_cores, tensor_cores,
#: cuda_compute, vram_gb, accelerator). Published NVIDIA/AMD/Intel
#: specifications for the named part - never measured, never from an artifact
#: (R3). The cuda_cores figures are the table's own: every consistent row
#: already equals per-GPU cores x gpu_per_node, so these are back-derived from
#: it and agree with the published spec.
#: vram is per GPU as the part ships it, which is where the reference API's
#: precise model strings pay off: an "A100 PCIe 80GB" is not the 40GB part the
#: table assumed.
GPU_VENDOR = {
    "A100":          (6912, 432, 8.0,  80, "cuda"),
    "A100-40":       (6912, 432, 8.0,  40, "cuda"),
    "H100":          (16896, 528, 9.0, 94, "cuda"),
    "V100":          (5120, 640, 7.0,  16, "cuda"),
    "V100-32":       (5120, 640, 7.0,  32, "cuda"),
    "P100":          (3584,   0, 6.0,  16, "cuda"),
    "K80":           (2496,   0, 3.7,  12, "cuda"),
    "M40":           (3072,   0, 5.2,  24, "cuda"),
    "RTX 6000":      (4608, 576, 7.5,  24, "cuda"),
    # Non-NVIDIA parts keep cuda_cores/tensor_cores at 0 and cuda_compute null
    # on purpose: they have compute units, but not CUDA ones, and the wing's
    # central trap is exactly the reader who treats "GPU" as "runs CUDA".
    "MI100":         (0, 0, None, 32,  "rocm"),
    "Ponte Vecchio": (0, 0, None, 128, "oneapi"),
}

#: reference-API gpu_model string -> the key above. The API names the exact
#: part; the table names a family. Mapping them by hand is what lets an
#: 80GB A100 be told apart from a 40GB one.
REF_GPU_MODEL = {
    "GA100 [A100 SXM4 80GB]":     "A100",
    "GA100 [A100 PCIe 80GB]":     "A100",
    "GA100 [A100 PCIe 40GB]":     "A100-40",
    "GH100 [H100 SXM5 94GB]":     "H100",
    "GV100GL [Tesla V100 PCIe 16GB]": "V100",
    "GV100GL [Tesla V100 PCIe 32GB]": "V100-32",
    "GV100GL [Tesla V100 SXM2 32GB]": "V100-32",
    "GP100GL [Tesla P100 PCIe 16GB]": "P100",
    "GP100GL [Tesla P100 SXM2 16GB]": "P100",
    "GK210GL [Tesla K80]":        "K80",
    "GM200GL [Tesla M40]":        "M40",
    "TU102GL [Quadro RTX 6000/8000]": "RTX 6000",
    "Arcturus GL-XL [Instinct MI100]": "MI100",
    "Ponte Vecchio XT (2 Tile) [Data Center GPU Max 1550]": "Ponte Vecchio",
}

#: The family name the table shows, per vendor key.
GPU_FAMILY = {"A100-40": "A100", "V100-32": "V100"}


def derive_gpu(entry: dict) -> dict | None:
    """GPU fields for one node type, or None to leave the row alone.

    gpu_per_node is the type's GUARANTEE, so a type where some nodes carry no
    accelerator at all reports 0 - the same conservatism the heterogeneous RAM
    case uses, and for the same reason: reserving the type can hand you any of
    its nodes. compute_gigaio is exactly this (10 of 14 have one GPU) and
    correctly stays a CPU type. compute_liqid is not: all 8 of its nodes carry
    an A100 that the table currently records as no GPU at all.
    """
    counts = {int(k): v for k, v in (entry.get("gpu_count") or {}).items()}
    models = entry.get("gpu_models") or {}
    if not counts or not models:
        return None
    if sum(counts.values()) < entry["node_count"]:
        return {"gpu_per_node": 0}          # not every node has one
    keys = {REF_GPU_MODEL.get(m) for m in models}
    if None in keys or len(keys) != 1:
        return None                          # unmapped or mixed: leave it
    key = keys.pop()
    per = min(counts)
    cores, tensor, cc, vram, accel = GPU_VENDOR[key]
    return {
        "accelerator": accel,
        "gpu_model": GPU_FAMILY.get(key, key),
        "gpu_per_node": per,
        "cuda_cores": cores * per,
        "tensor_cores": tensor * per,
        "cuda_compute": cc,
        "vram_gb_per_gpu": vram,
    }


def latest_capture() -> Path:
    caps = sorted(REF_DIR.glob("reference_api_*.json"))
    if not caps:
        raise SystemExit(f"no reference-API capture in {REF_DIR}; run "
                         "corpus_v2/tools/harvest_reference_api.py first")
    return caps[-1]


def _specific(models: dict) -> list[str]:
    """CPU model strings that actually name a model.

    "Intel Xeon" is a vendor, not a part, and appears on exactly the thin
    records this tool has to see past. Anything carrying a digit names
    something - including the ARM part id 461F0010.
    """
    return [m for m in models if any(c.isdigit() for c in m)]


def threads_by_cpu(ref: dict) -> dict:
    """(cpu_model, sockets) -> the highest thread count any type reports.

    Built only from types with ONE specific CPU model: on a heterogeneous type
    a thread count cannot be attributed to a particular CPU, and guessing which
    half of compute_gigaio reported 160 would put a fabricated fact into the
    thing that corrects facts.
    """
    out: dict[tuple[str, int], int] = {}
    for e in ref.values():
        models = _specific(e["cpu_models"])
        if len(models) != 1 or not e["smt_size"] or not e["smp_size"]:
            continue
        key = (models[0], max(int(k) for k in e["smp_size"]))
        out[key] = max(out.get(key, 0), max(int(k) for k in e["smt_size"]))
    return out


def derive(entry: dict, by_cpu: dict) -> dict:
    """One reference-API node_type block -> the values the table should carry."""
    ram = {int(k): v for k, v in entry["ram_gib"].items()}
    smt = {int(k): v for k, v in entry["smt_size"].items()}
    smp = {int(k): v for k, v in entry["smp_size"].items()}
    plats = entry.get("platform_type") or {"x86_64": 1}
    models = _specific(entry["cpu_models"])

    heterogeneous = len(models) > 1
    pick = min if heterogeneous else max

    platform = max(plats, key=plats.get)
    factor = SMT_FACTOR.get(platform, 2)
    sockets = pick(smp) if smp else None

    # Per model, prefer what the whole fleet knows about that CPU over what
    # this type's own records happened to say.
    per_model = [by_cpu.get((m, sockets), 0) for m in models]
    fleet = pick(per_model) if per_model and all(per_model) else 0
    threads = max(pick(smt) if smt else 0, fleet if not heterogeneous else 0)
    if heterogeneous and fleet:
        threads = fleet          # the weaker of the two machines, resolved
    threads = threads or None

    out = {
        "ram_gb": pick(ram) if ram else None,
        "threads": threads,
        "vcpus": threads // factor if threads else None,
        "platform": platform,
        "sockets": sockets,
        "heterogeneous": heterogeneous,
        "models": models,
        "warning": None,
    }

    # Cross-check against the core count the CPU names for itself. Only where
    # the type is one machine: on a heterogeneous type the stated cores belong
    # to one CPU and the derived value describes the other, so a mismatch there
    # would be an artefact of the comparison rather than a finding.
    stated = [int(m.group(1)) for mo in models
              if (m := _CORES_IN_MODEL.search(mo))]
    if stated and sockets and out["vcpus"] is not None and not heterogeneous:
        expect = stated[0] * sockets
        if expect != out["vcpus"]:
            out["warning"] = (f"derived {out['vcpus']} cores but "
                              f"{stated[0]}-core CPU x {sockets} sockets "
                              f"= {expect}")
    return out


def edit(text: str, values: dict, source: str) -> tuple[str, int]:
    """Rewrite ram_gb/vcpus inside node_types blocks only.

    Line-oriented rather than a YAML round-trip because the table opens with 52
    lines of hand-written provenance documentation that safe_dump would silently
    delete, and because `ranking.capability_score` has keys of the same names
    that must not be touched.
    """
    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.rstrip() == "node_types:")
    out, current, n = lines[:start + 1], None, 0

    for line in lines[start + 1:]:
        m = re.match(r"^  ([A-Za-z0-9_]+):\s*$", line)
        if m:
            current = m.group(1)
            out.append(line)
            continue
        if current and (f := re.match(r"^    (ram_gb|vcpus|accelerator|gpu_model|gpu_per_node|cuda_cores|tensor_cores|cuda_compute|vram_gb_per_gpu): (.*)$", line)):
            field, old = f.group(1), f.group(2).strip()
            new = values.get(current, {}).get(field, "KEEP")
            if new == "KEEP":
                # A row the reference API does not describe keeps its value -
                # but it must still be LABELLED, or "kept" is indistinguishable
                # from "never looked at", which is the whole point of the field.
                out.append(line)
            else:
                new_s = "null" if new is None else str(new)
                if new_s != old:
                    n += 1
                out.append(f"    {field}: {new_s}\n")
            # capability_source rides immediately after vcpus, so the numbers
            # and the claim about where they came from cannot drift apart in
            # a later hand edit.
            if field == "vcpus" and current in values:
                out.append(f"    capability_source: "
                           f"{values[current]['source']}\n")
            continue
        # A re-run must not stack duplicate provenance lines.
        if current and re.match(r"^    capability_source: ", line):
            continue
        out.append(line)
    return "".join(out), n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write the table (default: report only)")
    args = ap.parse_args()

    cap_path = latest_capture()
    cap = json.loads(cap_path.read_text())
    ref, probed = cap["node_types"], cap["_meta"]["probed_utc"]
    ref_source = cap_path.stem

    text = TABLE.read_text()
    table = yaml.safe_load(text)["node_types"]

    by_cpu = threads_by_cpu(ref)
    values, warnings, gpu_changes = {}, [], []
    print(f"{'node_type':<24} {'ram_gb':>14} {'vcpus':>14}   basis")
    for name in sorted(table):
        cur = table[name]
        e = ref.get(name)
        if not e:
            # Keeps its Blazar numbers; only gains a label saying so.
            values[name] = {"source": BLAZAR_SOURCE}
            print(f"{name:<24} {str(cur.get('ram_gb')):>14} "
                  f"{str(cur.get('vcpus')):>14}   KEPT (absent from "
                  f"reference API) <- {BLAZAR_SOURCE}")
            continue
        d = derive(e, by_cpu)
        values[name] = {"ram_gb": d["ram_gb"], "vcpus": d["vcpus"],
                        "source": ref_source}
        g = derive_gpu(e)
        if g:
            for field, val in g.items():
                if cur.get(field) != val:
                    gpu_changes.append(
                        f"{name}.{field}: {cur.get(field)} -> {val}")
            values[name].update(g)
        basis = (f"{'min' if d['heterogeneous'] else 'max'} of "
                 f"{len(e['cpu_models'])} model(s), {d['threads']}t/"
                 f"{d['sockets']}s {d['platform']}")
        if d["heterogeneous"]:
            basis += "  HETEROGENEOUS"
        ram_s = f"{cur.get('ram_gb')} -> {d['ram_gb']}"
        cpu_s = f"{cur.get('vcpus')} -> {d['vcpus']}"
        mark = " " if (cur.get("ram_gb") == d["ram_gb"]
                       and cur.get("vcpus") == d["vcpus"]) else "*"
        print(f"{name:<24} {ram_s:>14} {cpu_s:>14} {mark} {basis}")
        if d["warning"]:
            warnings.append(f"{name}: {d['warning']}")

    if gpu_changes:
        print("\nGPU FIELD CORRECTIONS")
        for c in gpu_changes:
            print(f"  {c}")

    if warnings:
        print("\nCORE-COUNT CROSS-CHECK MISMATCHES")
        for w in warnings:
            print(f"  {w}")
    else:
        print("\ncore-count cross-check: every CPU that names its own core "
              "count agrees with the derived vcpus.")

    new_text, n = edit(text, values, ref_source)
    print(f"\n{n} field(s) would change; capture {cap_path.name}, "
          f"probed {probed}")
    if not args.apply:
        print("report only; pass --apply to write")
        return 0
    TABLE.write_text(new_text)
    print(f"wrote {TABLE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
