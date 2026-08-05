"""phases: assign every triaged artifact to audit phase 1, 2, or 3. Stage 3.

Phase 1 is ten adversarially chosen artifacts. Not a random sample: the point
is to break the parser before it runs at scale, so each slot takes the hardest
available case in its category. A slot with no candidate is reported empty
rather than filled with an easier substitute, because a slot quietly filled
with an easy case reports coverage that does not exist.

Phase 2 is 25 artifacts stratified across api_family x record_type x
python_chi_era, two per cell wherever the population allows.

Phase 3 is everything remaining, with no per-artifact audit.

  python corpus_v2/tools/phases.py run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import load_catalog, normalize_repo  # noqa: E402
from triage import load_manifest                  # noqa: E402

CORPUS = HERE.parent
WORKSPACE = CORPUS.parent.parent
PHASES = CORPUS / "phases.tsv"

PHASE2_TARGET = 25
COLUMNS = ["artifact_id", "phase", "slot", "triage_class",
           "api_family_detected", "python_chi_era", "site_call_style",
           "selection_reason"]

BEARING = {"instructional", "evidence"}
TROVI_WRAPPER = "chameleoncloud/trovi_external_artifacts_deployment"


def f(row, key, default=0.0) -> float:
    try:
        return float(row[key])
    except (ValueError, KeyError, TypeError):
        return default


def i(row, key) -> int:
    try:
        return int(row[key])
    except (ValueError, KeyError, TypeError):
        return 0


def pick(pool, predicate, rank, taken):
    """Highest-ranking unclaimed row satisfying predicate, or None."""
    cands = [r for r in pool if r["artifact_id"] not in taken and predicate(r)]
    return sorted(cands, key=rank)[0] if cands else None


def build_phase1(rows, wrapper_ids):
    """Ten slots, each taking the hardest available case in its category."""
    taken: set[str] = set()
    out: list[tuple[str, dict | None, str]] = []
    bearing = [r for r in rows if r["triage_class"] in BEARING]

    def claim(slot, row, reason):
        if row:
            taken.add(row["artifact_id"])
        out.append((slot, row, reason))

    # 1. baremetal. The grammar has zero positive examples in this workspace
    #    outside forbidden_calls trap lists, so the parser has nothing local to
    #    validate against. Prefer the canonical pattern artifact by name.
    row = pick(bearing,
               lambda r: "bare-metal-experiment-pattern" in r["artifact_id"],
               lambda r: r["artifact_id"], taken)
    if row:
        claim("1_baremetal", row,
              "canonical Bare Metal Experiment Pattern; baremetal grammar has "
              "zero positive local examples to validate the parser against")
    else:
        row = pick(bearing, lambda r: r["api_family_detected"] == "baremetal",
                   lambda r: -i(r, "n_provisioning_cells"), taken)
        claim("1_baremetal", row,
              "closest baremetal artifact by detected api_family" if row else "")

    # 2. KVM. The brief names cloud-chi and kvm_gpu_artifact, so prefer those
    #    by repo slug before falling back to any kvm-family artifact.
    row = pick(bearing, lambda r: any(s in r["repo_url"].lower()
                                      for s in ("kvm_gpu_artifact", "cloud-chi")),
               lambda r: (-i(r, "n_provisioning_cells"), r["artifact_id"]), taken)
    named = row is not None
    if not row:
        row = pick(bearing, lambda r: r["api_family_detected"] == "kvm",
                   lambda r: -i(r, "n_provisioning_cells"), taken)
    claim("2_kvm", row,
          ("named KVM artifact (kvm_gpu_artifact / cloud-chi), most "
           "provisioning cells" if named else
           "KVM api_family, most provisioning cells") if row else "")

    # 3. Research artifact, lowest density, dispersed. Worst case for the
    #    fragment boundary heuristic.
    row = pick(bearing,
               lambda r: (r["triage_class"] == "evidence"
                          and r["dispersed"] == "True"
                          and i(r, "n_provisioning_cells") > 0),
               lambda r: (f(r, "provisioning_density"),
                          -i(r, "n_fragments_predicted")), taken)
    claim("3_dispersed_research", row,
          "evidence class, dispersed=True, lowest provisioning_density; worst "
          "case for the fragment boundary heuristic" if row else "")

    # 4. Over the size cap, to exercise sparse-checkout fallback.
    row = pick(rows, lambda r: r["fetch_status"] == "sparse",
               lambda r: -f(r, "repo_size_mb"), taken)
    claim("4_over_size_cap", row,
          "largest repo fetched via sparse-checkout fallback" if row else "")

    # 5. trovi_external_artifacts_deployment wrapper, the no-GitHub path.
    row = pick(rows, lambda r: r["artifact_id"] in wrapper_ids,
               lambda r: r["artifact_id"], taken)
    claim("5_trovi_wrapper", row,
          "links only the generic trovi_external_artifacts_deployment wrapper; "
          "exercises the no-GitHub path" if row else "")

    # 6. mlflow-chi NVIDIA VM variant. Holds content constant across
    #    api_family, so it is the sharpest test of grammar discrimination.
    row = pick(rows, lambda r: "mlflow" in r["artifact_id"]
               and "nvidia-vm" in r["artifact_id"],
               lambda r: r["artifact_id"], taken)
    if not row:
        row = pick(rows, lambda r: "mlflow" in r["artifact_id"]
                   and "vm-version" in r["artifact_id"],
                   lambda r: r["artifact_id"], taken)
    claim("6_mlflow_nvidia_vm", row,
          "mlflow-chi NVIDIA VM variant; content held constant across "
          "api_family, sharpest grammar-discrimination test" if row else "")

    # 7. context.choose_site rather than chi.use_site.
    row = pick(bearing, lambda r: r["site_call_style"] == "choose_site",
               lambda r: -i(r, "n_provisioning_cells"), taken)
    claim("7_choose_site", row,
          "site set via context.choose_site, not chi.use_site; choose_site is "
          "10 of 27 measured site-setting calls" if row else "")

    # 8. legacy or mixed era. legacy preferred: rarer, and the deprecated
    #    free-function surface is where the parser is least exercised.
    row = pick(bearing, lambda r: r["python_chi_era"] == "legacy",
               lambda r: -i(r, "n_provisioning_cells"), taken)
    era = "legacy"
    if not row:
        row = pick(bearing, lambda r: r["python_chi_era"] == "mixed",
                   lambda r: -i(r, "n_provisioning_cells"), taken)
        era = "mixed"
    claim("8_legacy_era", row,
          f"python_chi_era={era}, most provisioning cells" if row else "")

    # 9. Lowest triage confidence: the instructional/evidence boundary case.
    row = pick(bearing, lambda r: True,
               lambda r: (f(r, "triage_confidence"),
                          -i(r, "n_provisioning_cells")), taken)
    claim("9_lowest_confidence", row,
          f"lowest triage_confidence among code-bearing artifacts "
          f"({row['triage_confidence']}); the instructional/evidence boundary "
          f"case" if row else "")

    # 10. A negative. A false negative is invisible unless someone checks, and
    #     the hardest negative to clear is the one with the most code in it.
    row = pick(rows, lambda r: r["triage_class"] == "no-chameleon-code",
               lambda r: (-i(r, "total_bytes"), -i(r, "n_notebooks")), taken)
    claim("10_negative_control", row,
          "no-chameleon-code with the most scanned code, so a false negative "
          "would hide here first" if row else "")
    return out


def stratify(pool, taken):
    """(cells, phase2 selection). Two per cell where population allows."""
    cells: dict[tuple[str, str, str], list[dict]] = {}
    for r in pool:
        if r["artifact_id"] in taken:
            continue
        key = (r["api_family_detected"], r["triage_class"], r["python_chi_era"])
        cells.setdefault(key, []).append(r)

    # Deterministic within-cell order: most provisioning signal first.
    for v in cells.values():
        v.sort(key=lambda r: (-i(r, "n_provisioning_cells"), r["artifact_id"]))

    chosen: list[tuple[dict, tuple, str]] = []
    picked: set[str] = set()
    order = sorted(cells, key=lambda k: (-len(cells[k]), k))

    # Pass 1: two per cell, largest cells first, so common strata are
    # represented before the budget runs out.
    for key in order:
        for r in cells[key][:2]:
            if len(chosen) >= PHASE2_TARGET:
                break
            chosen.append((r, key, "stratum fill, 2 per cell"))
            picked.add(r["artifact_id"])
        if len(chosen) >= PHASE2_TARGET:
            break

    # Pass 2: spend any remainder on the largest cells, which carry the most
    # population risk per audited artifact.
    for key in order:
        if len(chosen) >= PHASE2_TARGET:
            break
        for r in cells[key]:
            if len(chosen) >= PHASE2_TARGET:
                break
            if r["artifact_id"] not in picked:
                chosen.append((r, key, "remainder, weighted to largest strata"))
                picked.add(r["artifact_id"])
    return cells, chosen


def run(wrapper_ids) -> int:
    rows = load_manifest()
    p1 = build_phase1(rows, wrapper_ids)
    taken = {r["artifact_id"] for _s, r, _x in p1 if r}

    bearing = [r for r in rows if r["triage_class"] in BEARING]
    cells, p2 = stratify(bearing, taken)
    taken |= {r["artifact_id"] for r, _k, _x in p2}

    out = []
    for slot, row, reason in p1:
        if row:
            out.append((row, 1, slot, reason))
    for row, key, reason in p2:
        out.append((row, 2, "|".join(key), reason))
    for r in rows:
        if r["artifact_id"] not in taken:
            out.append((r, 3, "", "remainder; no per-artifact audit, stratified "
                                  "sample of 20 drawn at audit time"))

    PHASES.write_text(
        "\t".join(COLUMNS) + "\n"
        + "".join("\t".join([
            r["artifact_id"], str(ph), slot, r["triage_class"],
            r["api_family_detected"], r["python_chi_era"],
            r["site_call_style"], reason]).replace("\n", " ") + "\n"
            for r, ph, slot, reason in out), encoding="utf-8")

    print("PHASE 1: adversarial selection\n")
    print(f"  {'slot':22} {'artifact_id':46} {'class':18} {'family':10} era")
    print("  " + "-" * 108)
    empty = []
    for slot, row, _reason in p1:
        if row:
            print(f"  {slot:22} {row['artifact_id'][:45]:46} "
                  f"{row['triage_class']:18} {row['api_family_detected']:10} "
                  f"{row['python_chi_era']}")
        else:
            empty.append(slot)
            print(f"  {slot:22} {'** NO CANDIDATE **':46}")
    if empty:
        print(f"\n  UNFILLED SLOTS: {', '.join(empty)}")

    print(f"\n\nPHASE 2: stratified, {len(p2)} of {PHASE2_TARGET} target\n")
    print(f"  {'api_family':12} {'record_type':14} {'era':10} {'pop':>4} {'picked':>7}")
    print("  " + "-" * 54)
    counts: dict[tuple, int] = {}
    for _r, key, _x in p2:
        counts[key] = counts.get(key, 0) + 1
    short = []
    for key in sorted(cells, key=lambda k: (-len(cells[k]), k)):
        got = counts.get(key, 0)
        print(f"  {key[0]:12} {key[1]:14} {key[2]:10} {len(cells[key]):>4} {got:>7}")
        if got < 2:
            short.append((key, len(cells[key]), got))
    if short:
        print("\n  CELLS BELOW 2 MEMBERS:")
        for key, pop, got in short:
            why = (f"population is only {pop}" if pop < 2
                   else "budget exhausted before this cell")
            print(f"    {'|'.join(key):46} picked {got}, {why}")

    n3 = sum(1 for _r, ph, _s, _x in out if ph == 3)
    print(f"\n\nPHASE 3: {n3} artifacts, no per-artifact audit")
    print(f"\n[written] {PHASES.relative_to(WORKSPACE)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run",))
    ap.parse_args()
    # Wrapper artifacts are those whose only repo is the Trovi import shim.
    ids = {a["artifact_id"] for a in load_catalog()
           if a["repo_urls"]
           and all(normalize_repo(u) == TROVI_WRAPPER for u in a["repo_urls"])}
    return run(ids)


if __name__ == "__main__":
    raise SystemExit(main())
