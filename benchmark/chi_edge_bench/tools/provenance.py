#!/usr/bin/env python3
"""Bind every collected answer to the exact prompt it answered.

The failure this prevents: edit an item's wording, regenerate, and every answer
already collected silently becomes an answer to a different question. Nothing in
the tree would notice - the files still exist, still parse, still score. The
numbers just quietly stop meaning what they say.

So each run directory carries `_manifest.json`:

    {"item": "R01", "prompt_sha256": "3f9a...", "collected": "2026-08-14T...",
     "provenance": "recorded"}

`recorded`  written at collection time; trustworthy.
`assumed`   backfilled for runs collected before manifests existed. It only
            asserts "this matched the prompt when we backfilled", so it cannot
            detect drift that happened earlier. Marked so nobody reads it as
            stronger evidence than it is.

  python tools/provenance.py --check      # report drift, exit 1 if any
  python tools/provenance.py --backfill   # stamp existing runs as `assumed`
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from chi_edge_bench.paths import items_dir, runs_dir, workspace
MANIFEST = "_manifest.json"


def prompt_sha(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def load_items() -> dict:
    """Every wing's items, merged by id.

    EVERY WING, not the pinned one. This read used to resolve `items_dir()`
    with no wing set, so it returned the edge wing's 134 items and nothing
    else - and `check()` skips any answer whose id it cannot find, on the
    reasonable-looking grounds that it is "scored elsewhere". The two together
    meant the chameleon wing's 136 manifested cells were silently passed over:
    `--check` reported "0 drift" over 60 run directories while the chameleon
    runs went entirely unexamined. An empty result set reading as a pass (P5)
    is the exact failure this gate exists to prevent, so it must not be the
    gate's own behaviour.

    Merging by id is safe because the wings' id spaces are disjoint (edge
    R/N/P/AV, chameleon CB/RB). That is asserted rather than assumed: a
    collision would mean one wing's prompt silently gating the other's
    answers, which is worse than the hole being fixed here.
    """
    from chi_edge_bench import paths

    out: dict = {}
    pinned = paths.wing()
    try:
        for name in paths.known_wings():
            paths.set_wing(name)
            for p in paths.items_dir().glob("*.yaml"):
                it = yaml.safe_load(p.read_text())
                prior = out.get(it["id"])
                if prior is not None and prior["prompt"] != it["prompt"]:
                    raise SystemExit(
                        f"item id {it['id']!r} exists in more than one wing with "
                        f"different prompts; provenance cannot tell which prompt "
                        f"a stored answer was collected against")
                out[it["id"]] = it
    finally:
        paths.set_wing(pinned)
    return out


def read_manifest(run_dir: Path) -> dict:
    p = run_dir / MANIFEST
    if not p.is_file():
        return {}
    try:
        return {r["item"]: r for r in json.loads(p.read_text())}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {}


def record(run_dir: Path, item_id: str, prompt: str, **extra) -> None:
    """Append/replace one item's provenance row. Called at collection time."""
    rows = read_manifest(run_dir)
    rows[item_id] = {
        "item": item_id,
        "prompt_sha256": prompt_sha(prompt),
        "collected": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provenance": "recorded",
        **extra,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / MANIFEST).write_text(
        json.dumps([rows[k] for k in sorted(rows)], indent=1) + "\n")


def run_dirs():
    for d in sorted(runs_dir().glob("*/*")):
        if d.is_dir():
            yield d


def check(items: dict):
    """Return (drift, unmanifested). Drift means an answer no longer matches
    the prompt it was collected against."""
    drift, unmanifested = [], []
    for d in run_dirs():
        man = read_manifest(d)
        rel = d.relative_to(workspace()).as_posix()
        for answer in sorted(d.glob("*.md")):
            stem = answer.stem
            if not answer.read_text(encoding="utf-8").strip():
                continue                      # empty cell: nothing was answered
            item = items.get(stem)
            if item is None:
                continue                      # scored elsewhere; not our business
            row = man.get(stem)
            if row is None:
                unmanifested.append(f"{rel}/{stem}")
                continue
            if row["prompt_sha256"] != prompt_sha(item["prompt"]):
                drift.append(f"{rel}/{stem}  collected against a DIFFERENT prompt "
                             f"({row.get('provenance', '?')}, {row.get('collected', '?')})")
    return drift, unmanifested


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    args = ap.parse_args()
    items = load_items()

    if args.backfill:
        n = 0
        for d in run_dirs():
            rows = dict(read_manifest(d))
            for answer in sorted(d.glob("*.md")):
                stem = answer.stem
                if stem in rows or stem not in items:
                    continue
                if not answer.read_text(encoding="utf-8").strip():
                    continue
                rows[stem] = {
                    "item": stem,
                    "prompt_sha256": prompt_sha(items[stem]["prompt"]),
                    "collected": datetime.fromtimestamp(
                        answer.stat().st_mtime, timezone.utc
                    ).isoformat(timespec="seconds"),
                    # Reconstructed, not observed. Cannot prove the prompt was
                    # the same when the answer was actually collected.
                    "provenance": "assumed",
                }
                n += 1
            if rows:
                (d / MANIFEST).write_text(
                    json.dumps([rows[k] for k in sorted(rows)], indent=1) + "\n")
        print(f"backfilled {n} rows as provenance=assumed")

    drift, unmanifested = check(items)
    print(f"\n{len(list(run_dirs()))} run directories checked")
    print(f"  prompt drift      : {len(drift)}")
    for x in drift[:20]:
        print(f"     x {x}")
    print(f"  unmanifested cells: {len(unmanifested)}")
    for x in unmanifested[:5]:
        print(f"     ? {x}")
    if drift:
        print("\nDRIFT: those answers respond to a prompt that no longer exists. "
              "Re-collect them or revert the item change.")
        return 1
    print("\nOK: every non-empty answer matches its item's current prompt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
