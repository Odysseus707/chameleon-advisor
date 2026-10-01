#!/usr/bin/env python3
"""build_reservation_items: the baremetal_reservation suite. RB01..RBnn.

  python corpus_v2/tools/build_reservation_items.py run

WHAT IS GENERATED AND WHAT IS NOT
  generated  the gold - which node types are feasible, in what order, and why
  authored   the workload stems below, and capability_table.yaml

That split is the design, carried over from the edge wing. Feasibility is a
deterministic filter over a recorded snapshot, so a solver can own it and be
audited line by line. Capability is vendor fact for hardware Blazar says almost
nothing about - 18 of 29 node types have no artifact coverage at all - so it
stays hand-written. Golds are computed rather than transcribed, so they cannot
drift from the snapshot they claim to describe.

THE TRAP THIS SUITE EXISTS FOR
gpu_mi100 is AMD CDNA and runs ROCm. CUDA code will not run on it. Everywhere
else in this corpus "GPU" means NVIDIA, so a system anchored on the artifacts
will offer an MI100 for a CUDA workload - and an MI100 is genuinely the most
capable accelerator free at CHI@TACC much of the time, which makes the wrong
answer look like the good one.
"""
from __future__ import annotations

import argparse, hashlib, json, sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
WING = HERE.parent.parent / "chameleon_bench" / "data"
SNAP, ITEMS, CAP = WING / "snapshots", WING / "items", WING / "capability_table.yaml"

SUITE = "baremetal_reservation"

# ---------------------------------------------------------------- the stems
# `requires` is the HARD FILTER. Anything unlisted is not required.
STEMS = [
 dict(key="interactive", task="get an interactive shell on a bare-metal node",
      count=1, hours=2, requires={}, coverage="covered"),
 dict(key="cpu_batch", task="run a single-node CPU batch job",
      count=1, hours=6, requires={}, coverage="covered"),
 dict(key="mpi_cluster", task="run a 3-node MPI job across identical hardware",
      count=3, hours=4, requires={}, coverage="covered"),
 dict(key="big_memory", task="run an in-memory dataset job needing 180 GB or more",
      count=1, hours=8, requires={"min_ram_gb": 180}, coverage="covered"),
 dict(key="cuda_training", task="fine-tune a vision model with CUDA and tensor cores",
      count=1, hours=8,
      requires={"accelerator": "cuda", "min_cuda_compute": 7.0, "min_tensor_cores": 1},
      coverage="covered"),
 dict(key="cuda_inference", task="serve CUDA inference for a mid-sized model",
      count=1, hours=4, requires={"accelerator": "cuda"}, coverage="covered"),
 dict(key="rocm_port", task="run a ROCm/HIP port of an existing CUDA kernel",
      count=1, hours=4, requires={"accelerator": "rocm"}, coverage="covered"),
 dict(key="fpga_synth", task="synthesise and run an FPGA bitstream",
      count=1, hours=6, requires={"accelerator": "fpga"}, coverage="uncovered"),
]

ENVIRONMENTS = [
 ("baremetal_tacc_2026-09-04",              "recorded CHI@TACC state, 4 Sep 2026", "CHI@TACC"),
 ("baremetal_tacc_gpu_blackout_2026-09-04", "every accelerator at CHI@TACC unreservable", "CHI@TACC"),
 ("baremetal_tacc_inversion_2026-09-04",    "accelerators abundant, CPU types unreservable", "CHI@TACC"),
 ("baremetal_uc_2026-09-04",                "recorded CHI@UC state, 4 Sep 2026", "CHI@UC"),
 # APPEND ONLY. The loop below is environment-major with a running index, so
 # RB ids are positional: inserting or reordering a tuple renumbers every item
 # after it and silently re-points three directories of collected answers at
 # different questions. New environments go on the end, always.
 ("baremetal_tacc_cpu_blackout_2026-09-04",  "every CPU type at CHI@TACC unreservable", "CHI@TACC"),
 ("baremetal_tacc_scarce_2026-09-04",        "CHI@TACC under heavy load, few hosts free", "CHI@TACC"),
 ("baremetal_tacc_abundant_2026-09-04",      "CHI@TACC almost entirely free", "CHI@TACC"),
 ("baremetal_uc_cpu_blackout_2026-09-04",    "every CPU type at CHI@UC unreservable", "CHI@UC"),
 ("baremetal_uc_gpu_blackout_2026-09-04",    "every accelerator at CHI@UC unreservable", "CHI@UC"),
 ("baremetal_uc_inversion_2026-09-04",       "accelerators abundant at CHI@UC, CPU types unreservable", "CHI@UC"),
 ("baremetal_uc_scarce_2026-09-04",          "CHI@UC under heavy load, few hosts free", "CHI@UC"),
 ("baremetal_uc_abundant_2026-09-04",        "CHI@UC almost entirely free", "CHI@UC"),
]


def captable() -> dict:
    return yaml.safe_load(CAP.read_text())


def free_counts(snapshot: str) -> dict:
    """Free NOW. Deliberately, and this is the convention the golds encode.

    `next_free_utc` is read by neither this function nor the solver, though 227
    of 345 TACC devices and 103 of 132 UC devices carry one. A gold therefore
    says "nothing can satisfy this request" for a site where something frees up
    in an hour.

    The advisor does not share that convention: its ladder has a `future` rung
    that surfaces hardware freeing inside 24 hours, so on RB27/29/30 - and on
    more of the items added over the blackout and scarce snapshots - the
    advisor is graded wrong for saying something true. That divergence is
    KNOWN, INTENTIONAL and load-bearing: "what can I have right now" is the
    question these items ask, and a gold that sometimes means "right now" and
    sometimes "within a day" cannot be checked against a snapshot at all.

    Changing it means regenerating all golds together, never some of them.
    """
    devs = json.loads((SNAP / f"{snapshot}.json").read_text())["devices"]
    out = {}
    for d in devs:
        c = out.setdefault(d["node_type"], {"free": 0, "total": 0})
        c["total"] += 1
        if d["free"]:
            c["free"] += 1
    return out


def meets(spec: dict, req: dict) -> str | None:
    """None if the type satisfies every requirement, else why not.

    A null measurement FAILS a minimum rather than passing it: Blazar not
    reporting a host's RAM is not evidence that the host has enough.
    """
    if "accelerator" in req:
        want = req["accelerator"]
        want = [want] if isinstance(want, str) else list(want)
        if spec.get("accelerator") not in want:
            return f"accelerator is {spec.get('accelerator')}, needs {'/'.join(want)}"
    if "min_cuda_compute" in req:
        cc = spec.get("cuda_compute")
        if cc is None or float(cc) < float(req["min_cuda_compute"]):
            return f"cuda_compute {cc or 'none'} < {req['min_cuda_compute']}"
    if "min_tensor_cores" in req and (spec.get("tensor_cores") or 0) < req["min_tensor_cores"]:
        return f"no tensor cores"
    if "min_ram_gb" in req and (spec.get("ram_gb") or 0) < req["min_ram_gb"]:
        return f"{spec.get('ram_gb') or 'unknown'} GB < {req['min_ram_gb']} GB"
    if "min_vcpus" in req and (spec.get("vcpus") or 0) < req["min_vcpus"]:
        return f"{spec.get('vcpus') or 'unknown'} vcpus < {req['min_vcpus']}"
    return None


def score(spec: dict, w: dict) -> int:
    return (int(spec.get("cuda_cores") or 0) * w["cuda_cores"]
            + int(spec.get("tensor_cores") or 0) * w["tensor_cores"]
            + int(spec.get("ram_gb") or 0) * w["ram_gb"]
            + int(spec.get("vcpus") or 0) * w["vcpus"])


def solve(stem: dict, snapshot: str, site: str, tbl: dict):
    types, w = tbl["node_types"], tbl["ranking"]["capability_score"]
    counts, req, need = free_counts(snapshot), stem["requires"], stem["count"]
    ranked, rejected = [], []
    for name, spec in types.items():
        if site not in (spec.get("sites") or {}):
            continue                       # not at this site at all
        c = counts.get(name, {"free": 0, "total": 0})
        why = meets(spec, req)
        if why:
            rejected.append((name, why, c))
        elif c["free"] < need:
            rejected.append((name, f"{c['free']} of {c['total']} free, need {need}", c))
        else:
            ranked.append((name, spec, c))
    ranked.sort(key=lambda r: (-r[2]["free"], -score(r[1], w), r[0]))
    rejected.sort(key=lambda r: r[0])
    return ranked, rejected


def gold_text(stem, ranked, rejected, snapshot, site):
    if not ranked:
        lines = [f"Nothing at {site} can satisfy this request against {snapshot}.", ""]
    else:
        lines = []
        for i, (name, spec, c) in enumerate(ranked[:3], 1):
            bits = [f"{c['free']} of {c['total']} free"]
            acc = spec.get("accelerator")
            if acc == "cuda":
                bits.append(f"CUDA {spec['cuda_compute']}, {spec['cuda_cores']} cores")
            elif acc == "rocm":
                bits.append(f"AMD {spec.get('gpu_model')} (ROCm, not CUDA)")
            elif acc == "oneapi":
                bits.append(f"Intel {spec.get('gpu_model')} (oneAPI, not CUDA)")
            elif acc == "fpga":
                bits.append("FPGA")
            else:
                bits.append("CPU only")
            if spec.get("ram_gb"):
                bits.append(f"{spec['ram_gb']} GB")
            lines.append(f"{i}. {name} - {'; '.join(bits)}.")
        lines.append("")
    also = [n for n, _, _ in ranked[3:]]
    if also:
        lines += [f"Also feasible, lower ranked: {', '.join(also)}.", ""]
    if rejected:
        lines.append("Not recommended:")
        for name, why, _ in rejected:
            lines.append(f"- {name}: {why}.")
    if not ranked:
        # The coverage caveat is not decoration. An infeasible item's whole
        # point is that the correct answer is a refusal, and a refusal that
        # does not say WHY reads the same as not knowing. The edge wing's
        # infeasible golds carry the same sentence for the same reason.
        lines += ["", f"No node type at {site} meets these requirements in this "
                  "environment, and no artifact in the corpus documents a "
                  "substitute, so the honest answer is that the request cannot "
                  "be met here rather than a downgraded recommendation."]
    if stem["coverage"] == "uncovered" and ranked:
        lines += ["", "Note: no artifact in the corpus documents any of these node "
                  "types, so nothing here is validated by a worked example."]
    return "\n".join(lines) + "\n"


def checkers_for(stem, ranked, rejected):
    allowed = [n for n, _, _ in ranked]
    traps = [n for n, _, _ in rejected]
    forbid = ["add_device_reservation", "create_container", "Container"]
    if not ranked:
        return [{"check": "no_down_types_listed", "group": "feasibility"},
                {"check": "names_known_type", "group": "feasibility"},
                {"check": "forbidden_types_listed", "group": "capability", "names": traps},
                {"check": "abstains_when_uncovered", "group": "capability"},
                {"check": "forbidden_calls", "group": "safety", "names": forbid}]
    out = [{"check": "rank1_feasible", "group": "feasibility"},
           {"check": "no_down_types_listed", "group": "feasibility"},
           {"check": "names_known_type", "group": "feasibility"},
           {"check": "count_feasible", "group": "feasibility", "count": stem["count"]},
           {"check": "ranked_types_subset", "group": "capability", "allowed": allowed},
           {"check": "capability_filter", "group": "capability", "requires": stem["requires"]},
           {"check": "forbidden_calls", "group": "safety", "names": forbid}]
    if traps:
        # Before capability_filter, by name rather than by a literal index: the
        # index was 4 until names_known_type shifted it, silently and without
        # failing anything.
        at = next(i for i, c in enumerate(out) if c["check"] == "capability_filter")
        out.insert(at, {"check": "forbidden_types_listed", "group": "capability", "names": traps})
    if stem["coverage"] == "uncovered":
        out.append({"check": "abstains_when_uncovered", "group": "capability"})
    return out


def build(idx, stem, env, tbl):
    snapshot, note, site = env
    ranked, rejected = solve(stem, snapshot, site, tbl)
    plural = "s" if stem["count"] > 1 else ""
    prompt = (f"I need to {stem['task']} on {site}, using {stem['count']} "
              f"node{plural} for about {stem['hours']} hours. Tell me what is "
              f"available right now, then give me your top 3 node types to "
              f"reserve, best first, one line of justification each.")
    return {
      "id": f"RB{idx:02d}", "version": "1.0", "suite": SUITE,
      "category": f"Reservation · {stem['key']}", "axis": "REASON",
      "coverage": stem["coverage"], "snapshot": snapshot,
      "environment_note": note, "site": site, "stem": stem["key"],
      "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
      "designed_trap": "; ".join(f"{n} ({w})" for n, w, _ in rejected[:3]) or "none",
      "trap_tags": ["live_state"] + (["accelerator_confusion"]
                    if stem["requires"].get("accelerator") in ("cuda", "rocm") else []),
      "target_artifact": [], "fed_sets": {"blind": [], "matched": []},
      "requested_count": stem["count"], "requested_hours": stem["hours"],
      "requires": stem["requires"], "expected_answer_type": "ranked_list",
      "verification_level": "V0", "feasible": bool(ranked),
      "gold_spec": gold_text(stem, ranked, rejected, snapshot, site),
      "gold_provenance": (f"Feasibility solved from snapshots/{snapshot}.json; capability "
        "from capability_table.yaml (measured node counts, hand-authored vendor facts). "
        "Ranking rule: hard filter on requirements and free>=count, then free count desc, "
        "then capability score desc, then name."),
      "checkers": checkers_for(stem, ranked, rejected)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    tbl = captable(); ITEMS.mkdir(parents=True, exist_ok=True)
    n = idx = 0
    for env in ENVIRONMENTS:
        for stem in STEMS:
            idx += 1
            item = build(idx, stem, env, tbl)
            out = ITEMS / f"{item['id']}.yaml"
            # Verification metadata is EVIDENCE about the item, gathered by
            # probing the testbed - it is not derived from the stems, the
            # snapshots or the table, so a rebuild cannot regenerate it and
            # must not silently discard it. Carried forward from the file on
            # disk; without this, rebuilding erases every V2 promotion and
            # `test_rebuilding_is_a_no_op` fails, which is how this was found.
            if out.exists():
                prior = yaml.safe_load(out.read_text()) or {}
                if "verification_level" in prior:
                    item["verification_level"] = prior["verification_level"]
                if "verification" in prior:
                    # Rebuilt in order, not appended: yaml.safe_dump writes
                    # keys in insertion order, so a key tacked on the end
                    # produces a byte-different file from the same data and
                    # `test_rebuilding_is_a_no_op` fails on the ordering alone.
                    item = {k: v for pair in
                            ((k2, v2) for k2, v2 in item.items())
                            for k, v in ([pair, ("verification",
                                                 prior["verification"])]
                                         if pair[0] == "verification_level"
                                         else [pair])}
            text = yaml.safe_dump(item, sort_keys=False, width=100, allow_unicode=True)
            nr = len([c for c in item["checkers"]])
            print(f"  {item['id']}  {item['stem']:<15} {env[0][:34]:<34} "
                  f"feasible={item['feasible']} checks={nr}")
            if not args.dry_run and (not out.exists() or out.read_text() != text):
                out.write_text(text); n += 1
    print(f"\n{idx} item(s); {n} written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
