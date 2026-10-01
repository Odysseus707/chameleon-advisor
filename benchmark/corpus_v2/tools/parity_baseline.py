"""parity_baseline: pin and verify the frozen v1 measurement surface.

This is the Q7 Level 1 + Level 2 + Level 3 check, in one reusable tool. It is
the gate that every later corpus_v2 run is diffed against.

  Level 1  content parity   sha256 of every watched file in every discovered
                            wing: items/, grounding/, extractions/, snapshots/,
                            artifacts/, baselines/ and data-root *.yaml (which
                            is what covers capability_table.yaml)
  Level 2  verdict parity   rescore all collected cells, byte-diff the CSV
  Level 3  gold-gate parity harness.validate_golds must stay green, and
                            exports/gate_report.json must be unchanged

Level 2 is the real one: it exercises extract_code, every checker, the AST
paths, group aggregation, and the V1 subprocess execution against the
synthetic snapshot. Files being unchanged is necessary and not sufficient,
because the scorer imports harness code that an expansion might touch.

Complements run_bench.py:81 provenance_hashes, which computes four rolling
group hashes at bench-run time for embedding in run metadata. That has no
per-file manifest, does not cover extractions/, and cannot diff. This does.

  python corpus_v2/tools/parity_baseline.py pin      # capture the baseline
  python corpus_v2/tools/parity_baseline.py verify   # diff against the pin

pin refuses to overwrite an existing pin unless --force is given, because
silently re-pinning is how a stale baseline gets blessed as a fresh one.

No network. No API calls. Read-only over harness/, items/, runs/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent                  # benchmark/corpus_v2/
BENCH = CORPUS.parent                 # benchmark/
WORKSPACE = BENCH.parent              # chameleon-work/
PARITY = CORPUS / "parity"

# What Level 1 watches inside each wing. Keys are stored workspace-relative so
# the manifest stays stable across machines.
#
# These are leaf patterns, and the wings they apply to are DISCOVERED rather
# than listed (see discover_wings). The original version hardcoded the parent
# as `benchmark/items/*.yaml`; the packaging refactor moved the data under
# chi_edge_bench/ and this tool went blind for a month. Hardcoding the parent
# was the bug. Enumerating the leaf names is fine - those are the benchmark's
# own vocabulary and do not move when packaging changes.
#
# `*.yaml` at the data root is what covers capability_table.yaml: hand-authored
# ground truth that every reservation verdict depends on, which the original
# four globs did not watch at all.
CONTENT_PATTERNS = [
    "items/*.yaml",
    "grounding/*.md",
    "extractions/*.yaml",
    "snapshots/*.json",
    "artifacts/*.yaml",      # a wing's pinned artifact registry
    "baselines/*.csv",       # shipped reference arms, quoted in the README
    "baselines/*.md",
    "*.yaml",                # capability tables and any other data-root config
]

#: A wing is a package directory under benchmark/ that ships a data/ tree.
WING_MARKER = "data"

PINNED_CSV = PARITY / "run_scores.baseline.csv"
PINNED_SUMMARY = PARITY / "run_summary.baseline.md"
PINNED_GATE = PARITY / "gate_report.baseline.json"
PINNED_CONTENT = PARITY / "content_manifest.sha256"
PINNED_META = PARITY / "baseline_meta.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def discover_wings() -> list[tuple[str, Path]]:
    """Every benchmark wing in this repo, as (package_name, data_dir).

    Discovered, not listed, so a new wing is protected the moment its data tree
    exists rather than when someone remembers to add it here. That is the whole
    point of this rewrite: the previous hardcoded path meant a second wing would
    have shipped with no Level 1 coverage and nothing would have said so.

    The wing list is recorded in baseline_meta.json, so a wing that later
    DISAPPEARS also fails - its keys vanish from the manifest and Level 1 goes
    red. Discovery adds coverage automatically; it never removes it silently.
    """
    wings = []
    for pkg in sorted(BENCH.iterdir()):
        if not pkg.is_dir() or pkg.name.startswith((".", "_")):
            continue
        data = pkg / WING_MARKER
        if data.is_dir():
            wings.append((pkg.name, data))
    if not wings:
        raise SystemExit(
            f"no benchmark wing found under {BENCH}: expected at least one "
            f"package directory containing a '{WING_MARKER}/' tree. Level 1 "
            "cannot protect a surface it cannot locate.")
    return wings


def content_manifest() -> list[tuple[str, str]]:
    """sha256 of every watched file across every discovered wing, sorted by key.

    A wing that contributes no files at all is a configuration error, not an
    empty set - it means the patterns no longer describe that wing's layout and
    Level 1 has gone blind to it while still reporting OK. Individual patterns
    are allowed to miss, because wings legitimately differ: the chameleon wing
    carries artifacts/ and the edge wing does not, and neither absence is a bug.
    """
    rows = []
    for name, data in discover_wings():
        hits = []
        for pattern in CONTENT_PATTERNS:
            hits.extend(p for p in sorted(data.glob(pattern)) if p.is_file())
        if not hits:
            raise SystemExit(
                f"wing '{name}' at {data} matched none of the content patterns "
                f"{CONTENT_PATTERNS}. Fix the patterns; a wing that matches "
                "nothing makes Level 1 blind to it.")
        rows.extend((str(p.relative_to(WORKSPACE)), sha256_file(p))
                    for p in dict.fromkeys(hits))   # dedupe, preserve order
    return sorted(rows)


def manifest_wing_counts() -> dict[str, int]:
    """{wing name: files watched}, for the pin metadata and for reporting."""
    counts = {}
    for name, data in discover_wings():
        seen = set()
        for pattern in CONTENT_PATTERNS:
            seen.update(p for p in data.glob(pattern) if p.is_file())
        counts[name] = len(seen)
    return counts


def render_content_manifest(rows) -> str:
    return "".join(f"{digest}  {key}\n" for key, digest in rows)


def manifest_digest(rows) -> str:
    """One hash standing for the whole content surface."""
    return sha256_bytes(render_content_manifest(rows).encode("utf-8"))


def parse_content_manifest(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.strip():
            digest, _, key = line.partition("  ")
            out[key] = digest
    return out


def run_scorer(csv_out: Path, md_out: Path) -> None:
    """Rescore every collected cell with the scorer's default flags.

    Default flags matter. --wrap-code is a recovery *analysis*: it rewrites
    unfenced answers in memory before scoring and flips verdicts on answers
    the extractor would otherwise not see. runs/ is the measurement record,
    so the baseline is the default read of it, not the recovered read.
    """
    cmd = [sys.executable, "-m", "chi_edge_bench.tools.score_runs",
           "--csv", str(csv_out), "--md", str(md_out)]
    proc = subprocess.run(cmd, cwd=BENCH, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"score_runs.py failed with exit {proc.returncode}")


def run_gold_gate(gate_out: Path) -> tuple[bool, str]:
    """harness.validate_golds writes exports/gate_report.json as a side effect.

    We copy that side effect out to gate_out and leave the live file as we
    found it, so running the gate never counts as touching exports/.
    """
    live_gate = BENCH / "exports" / "gate_report.json"
    before = live_gate.read_bytes() if live_gate.exists() else None
    proc = subprocess.run(
        [sys.executable, "-m", "chi_edge_bench.harness.validate_golds",
         "--suite", "core"],
        cwd=BENCH, capture_output=True, text=True)
    passed = proc.returncode == 0
    if live_gate.exists():
        gate_out.write_bytes(live_gate.read_bytes())
    if before is not None:
        live_gate.write_bytes(before)
    tail = proc.stdout.strip().splitlines()
    return passed, (tail[-1] if tail else "")


def count_cells() -> tuple[int, int]:
    """(total answer files, non-empty answer files) under runs/."""
    cells = [p for p in sorted(BENCH.glob("runs/*/*/*.md"))
             if len(p.relative_to(BENCH / "runs").parts) == 3]
    filled = sum(1 for p in cells if p.read_text(encoding="utf-8").strip())
    return len(cells), filled


def csv_status_counts(csv_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in csv_path.read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) > 3:
            counts[parts[3]] = counts.get(parts[3], 0) + 1
    return dict(sorted(counts.items()))


def do_pin(force: bool) -> int:
    if PINNED_META.exists() and not force:
        raise SystemExit(
            f"a pin already exists at {PINNED_META.relative_to(WORKSPACE)}.\n"
            "Re-pinning silently is how a stale baseline gets blessed as a fresh "
            "one. Run 'verify' first; pass --force only if you intend to move "
            "the baseline and can say why.")
    PARITY.mkdir(parents=True, exist_ok=True)

    total, filled = count_cells()
    print(f"[cells] {total} answer files under runs/, {filled} non-empty")

    print("[level 2] rescoring every collected cell ...")
    run_scorer(PINNED_CSV, PINNED_SUMMARY)
    csv_sha = sha256_file(PINNED_CSV)
    print(f"[level 2] run_scores sha256 {csv_sha}")
    print(f"[level 2] status counts {csv_status_counts(PINNED_CSV)}")

    print("[level 3] running gold gate ...")
    gate_ok, gate_line = run_gold_gate(PINNED_GATE)
    gate_sha = sha256_file(PINNED_GATE) if PINNED_GATE.exists() else None
    print(f"[level 3] gold gate {'PASS' if gate_ok else 'FAIL'} {gate_line}")
    print(f"[level 3] gate_report sha256 {gate_sha}")

    print("[level 1] hashing frozen content surface ...")
    rows = content_manifest()
    PINNED_CONTENT.write_text(render_content_manifest(rows), encoding="utf-8")
    content_sha = manifest_digest(rows)
    wing_counts = manifest_wing_counts()
    print(f"[level 1] wings: " + ", ".join(f"{n} ({c} files)"
                                           for n, c in wing_counts.items()))
    print(f"[level 1] {len(rows)} files, manifest digest {content_sha}")

    meta = {
        "pinned_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scorer_invocation": "python -m chi_edge_bench.tools.score_runs (default flags, no --wrap-code)",
        "cells_total": total,
        "cells_non_empty": filled,
        "run_scores_sha256": csv_sha,
        "run_summary_sha256": sha256_file(PINNED_SUMMARY),
        "gate_report_sha256": gate_sha,
        "gold_gate_passed": gate_ok,
        "content_manifest_sha256": content_sha,
        "content_file_count": len(rows),
        "content_patterns": list(CONTENT_PATTERNS),
        # Which wings were watched, and how many files each contributed. A wing
        # appearing or vanishing shows up here as well as in the manifest keys,
        # so 'we forgot to protect the new wing' is visible in one glance.
        "wings": manifest_wing_counts(),
        "csv_status_counts": csv_status_counts(PINNED_CSV),
    }
    PINNED_META.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"\n[pinned] {PARITY.relative_to(WORKSPACE)}")
    return 0


def do_verify() -> int:
    if not PINNED_META.exists():
        raise SystemExit("no pin found. Run 'pin' first.")
    meta = json.loads(PINNED_META.read_text())
    failures = []

    # Level 1: content parity
    rows = content_manifest()
    now_content = manifest_digest(rows)
    level1_ok = now_content == meta["content_manifest_sha256"]
    if not level1_ok:
        failures.append("LEVEL 1 content parity")
        pinned = parse_content_manifest(PINNED_CONTENT.read_text())
        current = dict(rows)
        for key in sorted(set(pinned) | set(current)):
            if pinned.get(key) != current.get(key):
                state = ("added" if key not in pinned else
                         "deleted" if key not in current else "modified")
                print(f"  content {state}: {key}")
    print(f"[level 1] content parity {'OK' if level1_ok else 'FAIL'}")

    # Level 2: verdict parity, the real one
    tmp_csv = PARITY / ".verify_run_scores.csv"
    tmp_md = PARITY / ".verify_run_summary.md"
    run_scorer(tmp_csv, tmp_md)
    now_csv = sha256_file(tmp_csv)
    level2_ok = now_csv == meta["run_scores_sha256"]
    if not level2_ok:
        failures.append("LEVEL 2 verdict parity")
        pin_map = {tuple(l.split(",")[:3]): l
                   for l in PINNED_CSV.read_text(encoding="utf-8").splitlines()[1:]}
        now_map = {tuple(l.split(",")[:3]): l
                   for l in tmp_csv.read_text(encoding="utf-8").splitlines()[1:]}
        changed = [k for k in sorted(set(pin_map) | set(now_map))
                   if pin_map.get(k) != now_map.get(k)]
        print(f"  {len(changed)} cell verdicts differ from the pin")
        for k in changed[:25]:
            print(f"    {'/'.join(k)}")
        if len(changed) > 25:
            print(f"    ... and {len(changed) - 25} more")
        print(f"  kept for inspection: {tmp_csv.relative_to(WORKSPACE)}")
    else:
        tmp_csv.unlink(missing_ok=True)
        tmp_md.unlink(missing_ok=True)
    print(f"[level 2] verdict parity {'OK' if level2_ok else 'FAIL'}")

    # Level 3: gold-gate parity
    tmp_gate = PARITY / ".verify_gate_report.json"
    gate_ok, _ = run_gold_gate(tmp_gate)
    now_gate = sha256_file(tmp_gate) if tmp_gate.exists() else None
    gate_same = now_gate == meta["gate_report_sha256"]
    if not gate_ok:
        failures.append("LEVEL 3 gold gate red")
    if not gate_same:
        failures.append("LEVEL 3 gate report changed")
    else:
        tmp_gate.unlink(missing_ok=True)
    print(f"[level 3] gold gate {'OK' if gate_ok else 'FAIL'}, "
          f"report {'OK' if gate_same else 'FAIL'}")

    if failures:
        print("\nPARITY VIOLATED: " + "; ".join(failures))
        return 1
    print("\nPARITY HOLDS: frozen measurement surface is byte-identical to the pin.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=("pin", "verify"))
    ap.add_argument("--force", action="store_true",
                    help="allow 'pin' to overwrite an existing pin")
    args = ap.parse_args()
    return do_pin(args.force) if args.mode == "pin" else do_verify()


if __name__ == "__main__":
    raise SystemExit(main())
