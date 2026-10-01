#!/usr/bin/env python3
"""make_variants: derived environments from a real bare-metal capture.

The base captures are recorded fact. These are perturbations of them, used to
ask the same workload question under different scarcity so an answer cannot
score well by memorising one state of the testbed. Every file written here
carries SYNTHETIC: true and names the capture it came from, so a recording and
a perturbation can never be mistaken for each other.

Variants mirror the edge wing's six environments:
  base        the capture itself (written by make_baremetal_snapshots.py)
  scarce      the most abundant CPU type reduced to a single free host
  cpu_blackout   every CPU-only type unreservable
  gpu_blackout   every accelerator type unreservable
  inversion   GPUs abundant, CPUs scarce - inverts the corpus's own bias
  abundant    everything free
"""
from __future__ import annotations

import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAP = HERE.parent.parent / "chameleon_bench" / "data" / "snapshots"
import yaml
CAP = HERE.parent.parent / "chameleon_bench" / "data" / "capability_table.yaml"


def accel_types() -> set:
    tbl = yaml.safe_load(CAP.read_text())["node_types"]
    return {t for t, v in tbl.items() if v["accelerator"] != "none"}


def set_free(devs, pred, free):
    for d in devs:
        if pred(d):
            d["free"] = free
            d["status"] = "free" if free else "busy"
            if not free:
                d["reservable"] = False


def variant(base: dict, name: str, accel: set) -> dict:
    d = json.loads(json.dumps(base))
    devs = d["devices"]
    counts = {}
    for x in devs:
        counts[x["node_type"]] = counts.get(x["node_type"], 0) + (1 if x["free"] else 0)
    cpu = [t for t in counts if t not in accel]

    if name == "scarce":
        top = max(cpu, key=lambda t: counts[t], default=None)
        if top:
            seen = [0]
            def pred(x, top=top, seen=seen):
                if x["node_type"] != top or not x["free"]:
                    return False
                seen[0] += 1
                return seen[0] > 1          # leave exactly one free
            set_free(devs, pred, False)
        note = f"{top} reduced to a single free host"
    elif name == "cpu_blackout":
        set_free(devs, lambda x: x["node_type"] not in accel, False)
        note = "every CPU-only type unreservable"
    elif name == "gpu_blackout":
        set_free(devs, lambda x: x["node_type"] in accel, False)
        note = "every accelerator type unreservable"
    elif name == "inversion":
        set_free(devs, lambda x: x["node_type"] in accel, True)
        set_free(devs, lambda x: x["node_type"] not in accel, False)
        note = "accelerators abundant, CPU types unreservable - inverts the corpus's own bias"
    elif name == "abundant":
        set_free(devs, lambda x: True, True)
        note = "everything free"
    else:
        raise SystemExit(f"unknown variant {name}")

    m = d["_meta"]
    m.update({"SYNTHETIC": True, "variant": name,
              "derived_from": base["_meta"].get("_self", "base capture"),
              "recorded": base["_meta"]["recorded"],
              "note": f"DERIVED, not recorded: {note}. Base capture "
                      f"{base['_meta']['site']} {base['_meta']['recorded']}."})
    tot = {}; free = {}
    for x in devs:
        tot[x["node_type"]] = tot.get(x["node_type"], 0) + 1
        free[x["node_type"]] = free.get(x["node_type"], 0) + (1 if x["free"] else 0)
    m["node_type_totals"] = tot; m["node_type_free"] = free
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    accel = accel_types()
    bases = [p for p in sorted(SNAP.glob("baremetal_*.json"))
             if not json.loads(p.read_text())["_meta"].get("SYNTHETIC")]
    if not bases:
        raise SystemExit(f"no base capture under {SNAP}")
    n = 0
    for b in bases:
        base = json.loads(b.read_text())
        base["_meta"]["_self"] = b.name
        stem = b.stem.rsplit("_", 1)[0]          # baremetal_tacc
        day = b.stem.rsplit("_", 1)[1]
        for v in ("scarce", "cpu_blackout", "gpu_blackout", "inversion", "abundant"):
            out = SNAP / f"{stem}_{v}_{day}.json"
            doc = variant(base, v, accel)
            text = json.dumps(doc, indent=1) + "\n"
            nfree = sum(1 for x in doc["devices"] if x["free"])
            print(f"  {out.name:<44} {nfree:>4} free / {len(doc['devices'])}")
            if not args.dry_run and (not out.exists() or out.read_text() != text):
                out.write_text(text); n += 1
    print(f"\n{n} file(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
