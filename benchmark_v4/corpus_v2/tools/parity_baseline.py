"""parity_baseline: pin and verify the frozen v1 measurement surface.

This is the Q7 Level 1 + Level 2 + Level 3 check, in one reusable tool. It is
the gate that every later corpus_v2 run is diffed against.

  Level 1  content parity   sha256 of items/*.yaml, grounding/A*.md,
                            extractions/A*.yaml, snapshots/*.json
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
CORPUS = HERE.parent                  # benchmark_v4/corpus_v2/
BENCH = CORPUS.parent                 # benchmark_v4/
WORKSPACE = BENCH.parent              # chameleon-work/
PARITY = CORPUS / "parity"

# The four content globs named in Q7 Level 1. Keys are stored workspace-relative
# so the manifest stays stable across machines.
#
# All four anchor at benchmark_v4/, including extractions/: there is no
# extractions/ at the workspace root. Anchoring it at the root makes the glob
# match nothing and Level 1 goes blind to those files without failing, so
# EXPECT_NONEMPTY below asserts every glob actually resolves.
CONTENT_GLOBS = [
    (BENCH, "items/*.yaml"),
    (BENCH, "grounding/A*.md"),
    (BENCH, "extractions/A*.yaml"),
    (BENCH, "snapshots/*.json"),
]

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


def content_manifest() -> list[tuple[str, str]]:
    """sha256 of every file in the four frozen globs, sorted by key.

    A glob that matches nothing is treated as a configuration error, not as an
    empty set. A mis-anchored glob would otherwise silently shrink the surface
    that Level 1 protects while still reporting OK.
    """
    rows = []
    for root, pattern in CONTENT_GLOBS:
        hits = [p for p in sorted(root.glob(pattern)) if p.is_file()]
        if not hits:
            raise SystemExit(
                f"content glob '{pattern}' anchored at {root} matched no files. "
                "Fix the anchor; an empty glob makes Level 1 blind.")
        rows.extend((str(p.relative_to(WORKSPACE)), sha256_file(p)) for p in hits)
    return sorted(rows)


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
    cmd = [sys.executable, str(BENCH / "tools" / "score_runs.py"),
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
    proc = subprocess.run([sys.executable, "-m", "harness.validate_golds"],
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
    print(f"[level 1] {len(rows)} files, manifest digest {content_sha}")

    meta = {
        "pinned_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scorer_invocation": "tools/score_runs.py (default flags, no --wrap-code)",
        "cells_total": total,
        "cells_non_empty": filled,
        "run_scores_sha256": csv_sha,
        "run_summary_sha256": sha256_file(PINNED_SUMMARY),
        "gate_report_sha256": gate_sha,
        "gold_gate_passed": gate_ok,
        "content_manifest_sha256": content_sha,
        "content_file_count": len(rows),
        "content_globs": [f"{r.name}/{g}" for r, g in CONTENT_GLOBS],
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
