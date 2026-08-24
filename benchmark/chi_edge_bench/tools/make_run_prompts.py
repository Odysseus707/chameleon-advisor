#!/usr/bin/env python3
"""Generate run prompts for every item x condition into prompts/<condition>/<ITEM>.txt.

For each item YAML in items/ and each condition in its fed_sets:
  * blind (no fed artifacts): the file is the item prompt verbatim, nothing else.
  * fed conditions: a fixed wrapper that prepends the grounding material for each
    fed artifact (in listed order) as reference material, then the question.

Only pyyaml + stdlib. Reads items/ and grounding/; writes prompts/. Nothing else
is touched.
"""

import json
import sys
from pathlib import Path

import yaml

from chi_edge_bench.paths import (grounding_dir, items_dir, prompts_dir,
                                  snapshots_dir, workspace)

# Shipped data: fixed for the life of the process, safe as module constants.
ITEMS_DIR = items_dir()
GROUNDING_DIR = grounding_dir()
SNAPSHOTS_DIR = snapshots_dir()
# The output directory is NOT a module constant: prompts_dir() must be read
# after the CLI applies --workspace, or the flag is silently ignored.

INTRO = ("Here is reference material about CHI@Edge on Chameleon Cloud that may "
         "be relevant to my question.")
REF_OPEN = "=== REFERENCE MATERIAL ==="
REF_CLOSE = "=== END REFERENCE MATERIAL ==="

# The `with_listing` availability arm gets its own condition directory rather
# than overwriting blind/, so existing runs keep matching their prompt hashes.
LISTING_CONDITION = "blind_listing"
LISTING_INTRO = ("Here is the current device availability on CHI@Edge, as reported "
                 "by the reservation service.")
AVAIL_OPEN = "=== DEVICE AVAILABILITY ==="
AVAIL_CLOSE = "=== END DEVICE AVAILABILITY ==="


def build_fed(prompt: str, artifacts: list[str]) -> str:
    """Wrapper: intro, reference material (artifacts separated by blank lines), question."""
    material = "\n\n".join(
        (GROUNDING_DIR / f"{a}.md").read_text() for a in artifacts
    )
    return "\n".join([
        INTRO,
        REF_OPEN,
        material,
        REF_CLOSE,
        "",
        "Question: " + prompt,
    ])


def build_listing(prompt: str, snapshot: str) -> str:
    """Wrapper: the item's OWN snapshot as a device table, then the question.

    This is the `with_listing` availability arm. Blind prompts ask "what is
    available right now" and supply nothing, so they test whether a system can
    *fetch* live state. Handing the state over instead tests whether it can
    *reason over* state - the only answerable form of the question for a system
    with no availability backend, and the arm that separates genuine transfer
    (H1) from live state substituting for coverage (H2).

    Counts are per device_type with all three states kept separate: `down` is
    neither free nor reserved, and collapsing it would hide the trap the
    reservation suite is built around.
    """
    devices = json.loads((SNAPSHOTS_DIR / f"{snapshot}.json").read_text())["devices"]
    rows: dict[str, list[int]] = {}
    for d in devices:
        row = rows.setdefault(d["device_type"], [0, 0, 0, 0])
        status = d.get("status")
        if status == "free":
            row[0] += 1
        elif status == "busy":
            row[1] += 1
        elif status == "down":
            row[2] += 1
        row[3] += 1

    header = "%-32s %6s %6s %6s %6s" % ("device_type", "free", "busy", "down", "total")
    body = [
        "%-32s %6d %6d %6d %6d" % (mt, *counts)
        for mt, counts in sorted(rows.items(), key=lambda kv: -kv[1][3])
    ]
    totals = [sum(r[i] for r in rows.values()) for i in range(4)]
    body.append("%-32s %6d %6d %6d %6d" % ("TOTAL", *totals))

    return "\n".join([
        LISTING_INTRO,
        AVAIL_OPEN,
        "\n".join([header] + body),
        AVAIL_CLOSE,
        "",
        "Question: " + prompt,
    ])


def main() -> int:
    manifest = []  # (relpath, size_bytes)
    for item_path in sorted(ITEMS_DIR.glob("*.yaml")):
        item = yaml.safe_load(item_path.read_text())
        item_id = item["id"]
        prompt = item["prompt"]
        fed_sets = item.get("fed_sets") or {}
        for condition, artifacts in fed_sets.items():
            if condition == "blind" or not artifacts:
                content = prompt
            else:
                content = build_fed(prompt, artifacts)
            out_dir = prompts_dir() / condition
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{item_id}.txt"
            out_path.write_text(content)
            manifest.append((out_path.relative_to(workspace()).as_posix(),
                             len(content.encode("utf-8"))))

        # Availability arm, written to its own condition directory so that no
        # existing prompt changes: provenance.py binds each collected answer to
        # sha256(prompt), and rewriting one would invalidate every existing run.
        if "with_listing" in (item.get("availability_arm") or []) and item.get("snapshot"):
            content = build_listing(prompt, item["snapshot"])
            out_dir = prompts_dir() / LISTING_CONDITION
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{item_id}.txt"
            out_path.write_text(content)
            manifest.append((out_path.relative_to(workspace()).as_posix(),
                             len(content.encode("utf-8"))))

    width = max((len(p) for p, _ in manifest), default=0)
    print(f"Wrote {len(manifest)} prompt files under {prompts_dir()}/\n")
    for rel, size in manifest:
        print(f"  {rel:<{width}}  {size:>7,} bytes")
    print(f"\nTotal: {sum(s for _, s in manifest):,} bytes across {len(manifest)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
