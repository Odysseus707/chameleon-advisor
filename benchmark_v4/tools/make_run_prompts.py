#!/usr/bin/env python3
"""Generate run prompts for every item x condition into prompts/<condition>/<ITEM>.txt.

For each item YAML in items/ and each condition in its fed_sets:
  * blind (no fed artifacts): the file is the item prompt verbatim, nothing else.
  * fed conditions: a fixed wrapper that prepends the grounding material for each
    fed artifact (in listed order) as reference material, then the question.

Only pyyaml + stdlib. Reads items/ and grounding/; writes prompts/. Nothing else
is touched.
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ITEMS_DIR = ROOT / "items"
GROUNDING_DIR = ROOT / "grounding"
PROMPTS_DIR = ROOT / "prompts"

INTRO = ("Here is reference material about CHI@Edge on Chameleon Cloud that may "
         "be relevant to my question.")
REF_OPEN = "=== REFERENCE MATERIAL ==="
REF_CLOSE = "=== END REFERENCE MATERIAL ==="


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
            out_dir = PROMPTS_DIR / condition
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{item_id}.txt"
            out_path.write_text(content)
            manifest.append((out_path.relative_to(ROOT).as_posix(),
                             len(content.encode("utf-8"))))

    width = max((len(p) for p, _ in manifest), default=0)
    print(f"Wrote {len(manifest)} prompt files under {PROMPTS_DIR.relative_to(ROOT)}/\n")
    for rel, size in manifest:
        print(f"  {rel:<{width}}  {size:>7,} bytes")
    print(f"\nTotal: {sum(s for _, s in manifest):,} bytes across {len(manifest)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
