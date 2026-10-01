"""render_grounding: pinned tree -> one grounding document per artifact. Stage 6.

Deterministic. No LLM, no network, no API cost: the same tree always produces
the same bytes, so a grounding doc is a pure function of the commit it names.

WHAT A GROUNDING DOC IS FOR
It is the text an assistant is *fed* about an artifact. So it must carry the
provisioning code and the prose that explains it, and as little else as
possible. The edge wing's six were hand-curated; 91 cannot be, hence this.

FORMAT - matched to chi_edge_bench/data/grounding/A1.md so both wings read the
same way:

    # <title>                  from the README's first heading, else the repo
    <README body>
    ---
    # <path/to/notebook.ipynb>
    ## [markdown]              cells kept interleaved, because the prose is
    <text>                     what says WHY a node type was chosen
    ## [code]
    ```python
    ...
    ```
    # <path/to/script.py>
    ```python
    ...
    ```

Notebook markdown cells are kept deliberately. `detect._notebook_cells` returns
code only, which is right for triage and wrong here: "we use compute_skylake
because the FPGA nodes are oversubscribed" lives in a markdown cell, and that
sentence is exactly what makes the artifact groundable.

SELECTION, highest priority first. Anything not matched is left out.
  1. README*                             the human framing
  2. .ipynb holding a provisioning call   where CHI setup actually lives
  3. .py holding a provisioning call
  4. Dockerfile / *.yml / *.yaml / *.sh naming a resource literal

SIZE. Two limits, because one was demonstrably wrong (see the comment on
SOFT_MAX). Notebooks are guaranteed up to HARD_MAX; scripts and configs share
SOFT_MAX and are dropped first. Truncation is announced in-band and recorded in
the registry - a reader must never mistake a trimmed doc for a complete one.

HARD_MAX is not only about disk. A grounding doc exists to be FED, and 200 KB is
already ~50k tokens for a single artifact; a document too large to put in a
prompt is not made more useful by being complete. As of the corrected
provisioning filter no artifact reaches either limit (largest is 57 KB), so the
caps are a guard against future growth rather than something currently binding.

  python corpus_v2/tools/render_grounding.py run
  python corpus_v2/tools/render_grounding.py run --dry-run
  python corpus_v2/tools/render_grounding.py run --only A7 A10
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import warnings
from pathlib import Path

# Parsing other people's notebooks means compiling source full of regex strings
# written without raw prefixes. The SyntaxWarnings are about THEIR code, not
# ours, and there are hundreds; they would bury this tool's actual output.
warnings.filterwarnings("ignore", category=SyntaxWarning)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import normalize_repo                               # noqa: E402
from detect import (IMPORT_ROOTS, SKIP_DIRS, STRONG_CALLS,        # noqa: E402
                    WEAK_CALLS, WEAK_CONSTRUCTORS, _scan_source,
                    _strip_magics)
from fetch import repo_dir                                       # noqa: E402
from rank import FLAVOR_RE, GPU_RE, NODE_TYPE_RE, SITE_RE        # noqa: E402
from select_wing import (ARTIFACTS_DIR, WING, WORKSPACE,         # noqa: E402
                         load_registry, render_artifact)

GROUNDING_DIR = WING / "grounding"

#: Budget for SUPPORTING material - .py scripts and configs. The edge wing's
#: largest hand-curated doc is 36 KB, so 60 KB leaves headroom.
SOFT_MAX = 60_000

#: Absolute ceiling, including guaranteed content. Nothing currently reaches it.
HARD_MAX = 200_000

# Why two limits rather than one.
#
# The first version had a single 60 KB cap applied in priority order, which
# sounds fair and was not: measured over the 91, it discarded 49 provisioning
# NOTEBOOKS across six artifacts - A48 lost 27 of 32 - while keeping .py files
# that happened to sort earlier. That is backwards. Notebooks are where CHI
# provisioning lives and are the reason a grounding doc exists at all.
#
# So READMEs and notebooks are guaranteed up to HARD_MAX, and scripts/configs
# compete for whatever is left under SOFT_MAX. The ordering is what matters and
# it is kept even though, after has_provisioning was fixed, the corpus no longer
# comes near either limit: the bug that made it bind could recur, and the cost of
# keeping the guarantee is zero.
GUARANTEED_PRIORITIES = (1, 2)

#: Skip individual files above this: a multi-megabyte notebook is output images,
#: not code, and would spend the whole budget on one section.
MAX_SECTION_BYTES = 40_000

#: A README must be prose. Matching bare "readme*" swallowed A23's only
#: provisioning notebook (readme-remoteserver-chi.ipynb): it was read as raw
#: JSON, then dropped for exceeding MAX_SECTION_BYTES, so the artifact silently
#: lost the very file it was selected for.
README_SUFFIXES = {"", ".md", ".rst", ".txt", ".markdown"}

CONFIG_NAMES = {"dockerfile", "docker-compose.yml", "docker-compose.yaml"}
CONFIG_SUFFIXES = (".yml", ".yaml", ".sh")
FENCE = {".py": "python", ".sh": "bash", ".yml": "yaml", ".yaml": "yaml"}

RESOURCE_RES = (SITE_RE, NODE_TYPE_RE, FLAVOR_RE, GPU_RE)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read_text(p: Path) -> str:
    try:
        if p.stat().st_size > 20_000_000:
            return ""
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def has_provisioning(src: str) -> bool:
    """Does this code unit actually provision Chameleon resources?

    `_scan_source` returns (every call name, every import root) - NOT
    (strong, weak). Destructuring it as the latter made this function answer
    "does the file contain any function call at all", which flagged 3008 files
    in A48 and filled its grounding doc with jax internals. The names have to be
    intersected with detect's vocabulary explicitly.

    Strong calls are unambiguously Chameleon and stand alone. Weak calls
    (`execute`, `upload`, `Server`) collide with ordinary Python, so they count
    only alongside a chi-family import - the same rule triage.py applies.
    """
    calls, imports = _scan_source(_strip_magics(src))
    if calls & STRONG_CALLS:
        return True
    return bool(imports & IMPORT_ROOTS
                and calls & (WEAK_CALLS | WEAK_CONSTRUCTORS))


def names_a_resource(text: str) -> bool:
    return any(r.search(text) for r in RESOURCE_RES)


def walk(root: Path):
    """Every file worth looking at, skipping vendored and VCS trees."""
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(root)
        if SKIP_DIRS & set(rel.parts):
            continue
        yield p, rel


#: Markdown cells within this many cells of a provisioning cell are kept, since
#: the sentence explaining a node-type choice sits next to the call, not in it.
CONTEXT_RADIUS = 1


def notebook_sections(path: Path) -> list[str]:
    """The provisioning narrative of a notebook, not the whole notebook.

    Taking notebooks whole was the first version and it was wrong: a typical
    artifact notebook is three provisioning cells and sixty cells of matplotlib,
    so whole-notebook sections spent the size budget on analysis code and pushed
    *other notebooks out of the document altogether* - 8 of A8's 12, measured.
    Cell-level selection is what brings a 91-artifact corpus down from 3.2 MB to
    706 KB while keeping strictly more provisioning in it.

    So: keep cells that provision, keep the markdown immediately around them
    because that is where the reasoning lives, keep the notebook's opening
    markdown for framing, and elide everything else with a visible marker.
    Order is preserved throughout - a grounding doc is read top to bottom, and a
    code cell divorced from the sentence above it loses the reason for its
    choices.
    """
    import json
    try:
        nb = json.loads(read_text(path) or "{}")
    except (json.JSONDecodeError, RecursionError):
        return []

    cells = []
    for c in nb.get("cells", []):
        if not isinstance(c, dict):
            continue
        src = c.get("source", "")
        src = "".join(src) if isinstance(src, list) else str(src)
        if src.strip() and c.get("cell_type") in ("markdown", "code"):
            cells.append((c["cell_type"], src.rstrip()))
    if not cells:
        return []

    provisioning = {i for i, (k, s) in enumerate(cells)
                    if k == "code" and has_provisioning(s)}
    if not provisioning:
        return []

    keep = set(provisioning)
    for i in provisioning:
        for j in range(i - CONTEXT_RADIUS, i + CONTEXT_RADIUS + 1):
            if 0 <= j < len(cells) and cells[j][0] == "markdown":
                keep.add(j)
    # The opening markdown states what the notebook is for.
    for i, (kind, _s) in enumerate(cells):
        if kind == "markdown":
            keep.add(i)
            break

    out, elided = [], 0
    for i, (kind, src) in enumerate(cells):
        if i not in keep:
            elided += 1
            continue
        if elided:
            out.append(f"<!-- {elided} cell(s) omitted: no provisioning -->\n")
            elided = 0
        if kind == "markdown":
            out.append("## [markdown]\n\n" + src + "\n")
        else:
            out.append("## [code]\n\n```python\n" + src + "\n```\n")
    if elided:
        out.append(f"<!-- {elided} cell(s) omitted: no provisioning -->\n")
    return out


def collect_sections(root: Path) -> list[tuple[int, str, str]]:
    """(priority, path, body) for everything that earns a place, in order."""
    readme, notebooks, scripts, configs = [], [], [], []

    for p, rel in walk(root):
        name, suffix = p.name.lower(), p.suffix.lower()
        posix = rel.as_posix()

        if (name.startswith("readme") and len(rel.parts) == 1
                and suffix in README_SUFFIXES):
            body = read_text(p)
            if body.strip():
                readme.append((1, posix, body.rstrip() + "\n"))
            continue

        if suffix == ".ipynb":
            # Returns [] unless at least one cell provisions, so this is both
            # the selection test and the extraction.
            cells = notebook_sections(p)
            if cells:
                notebooks.append((2, posix, "\n".join(cells)))
            continue

        if suffix == ".py":
            body = read_text(p)
            if body.strip() and has_provisioning(body):
                scripts.append((3, posix, f"```python\n{body.rstrip()}\n```\n"))
            continue

        if name in CONFIG_NAMES or suffix in CONFIG_SUFFIXES:
            body = read_text(p)
            if body.strip() and names_a_resource(body):
                lang = FENCE.get(suffix, "")
                configs.append((4, posix,
                                f"```{lang}\n{body.rstrip()}\n```\n"))

    out = []
    for group in (readme, notebooks, scripts, configs):
        for pri, posix, body in group:
            if len(body.encode("utf-8")) <= MAX_SECTION_BYTES:
                out.append((pri, posix, body))
    return out


def title_of(sections, rec) -> str:
    """The README's first heading, else the repo name. Never invented."""
    for pri, _posix, body in sections:
        if pri != 1:
            continue
        for line in body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return rec["repo_url"].rstrip("/").rsplit("/", 1)[-1]


def _drop_leading_h1(body: str, title: str) -> str:
    """Remove the README's opening `# Title` when we have already emitted it."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if line.startswith("# ") and line[2:].strip() == title:
            return "\n".join(lines[i + 1:]).lstrip("\n") + "\n"
        break
    return body


def render(rec, sections) -> tuple[str, bool, int]:
    """(document, truncated, sections_kept)."""
    title = title_of(sections, rec)
    head = [f"# {title}\n\n",
            f"<!-- {rec['id']} | {rec['artifact_id']} -->\n",
            f"<!-- source: {rec['repo_url']} @ {rec['pinned_sha']} -->\n",
            "<!-- generated by corpus_v2/tools/render_grounding.py; "
            "do not hand-edit -->\n\n"]
    # The title is lifted FROM the README's own H1, so emitting the README
    # verbatim underneath would print it twice.
    readme = [(p, x, _drop_leading_h1(b, title)) for p, x, b in sections
              if p == 1]
    notebooks = [s for s in sections if s[0] == 2]
    support = [s for s in sections if s[0] not in GUARANTEED_PRIORITIES]

    parts = list(head)
    for _pri, _posix, body in readme:
        parts.append(body)
    if notebooks or support:
        parts.append("\n---\n")

    used = len("".join(parts).encode("utf-8"))
    kept, dropped = len(readme), []

    # Guaranteed: notebooks are the provisioning narrative. Only HARD_MAX stops
    # them, and when it does the document says which ones were lost.
    for _pri, posix, body in notebooks:
        block = f"\n# {posix}\n\n{body}"
        size = len(block.encode("utf-8"))
        if used + size > HARD_MAX:
            dropped.append(posix)
            continue
        parts.append(block)
        used += size
        kept += 1

    # Supporting material competes for what is left under the soft budget, and
    # never displaces a notebook because it is only considered after them.
    for _pri, posix, body in support:
        block = f"\n# {posix}\n\n{body}"
        size = len(block.encode("utf-8"))
        if used + size > max(SOFT_MAX, used):
            dropped.append(posix)
            continue
        parts.append(block)
        used += size
        kept += 1

    if dropped:
        # In-band, so a reader of the file itself cannot mistake a trimmed doc
        # for a complete one. The registry records it too, for querying.
        parts.append(
            f"\n---\n\n<!-- TRUNCATED: {len(dropped)} file(s) omitted. "
            f"Notebooks are kept up to {HARD_MAX:,} B; supporting scripts and "
            f"configs share a {SOFT_MAX:,} B budget and are dropped first. "
            f"Omitted: {', '.join(dropped[:20])}"
            f"{' ...' if len(dropped) > 20 else ''} -->\n")
    return "".join(parts), bool(dropped), kept


def verify_pin(rec) -> tuple[Path | None, str]:
    """The tree must still be at the commit the record pins.

    Rendering from a moved tree would produce a document whose header claims a
    commit it does not come from - a provenance lie no later check could catch,
    because the document is the only evidence of what was read.
    """
    repo = repo_dir(normalize_repo(rec["repo_url"]))
    if not repo.is_dir():
        return None, "no clone"
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    head = p.stdout.strip()
    if p.returncode != 0 or len(head) != 40:
        return None, "not a git repo"
    if head != rec["pinned_sha"]:
        return None, f"tree moved: at {head[:8]}, pinned {rec['pinned_sha'][:8]}"
    return repo, ""


def run(dry_run: bool, only: list[str]) -> int:
    reg = load_registry()
    records = [r for r in reg["artifacts"] if not only or r["id"] in only]
    GROUNDING_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[grounding] {len(records)} artifacts, cap {SOFT_MAX:,}/{HARD_MAX:,} B\n")
    wrote, unchanged, truncated, failed = 0, 0, [], []
    total = 0

    for rec in records:
        repo, why = verify_pin(rec)
        if repo is None:
            failed.append((rec["id"], why))
            continue
        sections = collect_sections(repo)
        if not sections:
            failed.append((rec["id"], "nothing matched the selection rules"))
            continue
        doc, was_trunc, kept = render(rec, sections)
        size = len(doc.encode("utf-8"))
        total += size
        if was_trunc:
            truncated.append(rec["id"])

        # Content identity, ignoring the header comments that carry the id.
        # Six repo+commit pairs back 15 of the 91 artifacts, so their grounding
        # bodies are byte-identical. An item that targets one and feeds another
        # as `heldout` would be feeding the SAME text, which silently destroys
        # the held-out condition the H0/H1 instrument rests on. Recording the
        # group makes that collision detectable instead of invisible.
        rec["content_group"] = sha256_text(
            re.sub(r"<!--.*?-->", "", doc, flags=re.S))[:12]
        rec["grounding_bytes"] = size
        rec["grounding_sha256"] = sha256_text(doc)
        rec["grounding_truncated"] = was_trunc
        rec["grounding_sections"] = kept

        if dry_run:
            continue
        path = GROUNDING_DIR / f"{rec['id']}.md"
        if path.exists() and path.read_text(encoding="utf-8") == doc:
            unchanged += 1
        else:
            path.write_text(doc, encoding="utf-8")
            wrote += 1
        apath = ARTIFACTS_DIR / f"{rec['id']}.yaml"
        atext = render_artifact(rec)
        if apath.read_text(encoding="utf-8") != atext:
            apath.write_text(atext, encoding="utf-8")

    ok = len(records) - len(failed)
    print(f"  rendered   {ok}/{len(records)}")
    if ok:
        print(f"  total      {total:,} B, mean {total // max(ok, 1):,} B")
    print(f"  truncated  {len(truncated)}"
          + (f": {', '.join(truncated[:12])}" if truncated else ""))
    if failed:
        print(f"\n  FAILED ({len(failed)}):")
        for aid, why in failed:
            print(f"    {aid:<5} {why}")
        print("  A record with no grounding cannot be fed to anything;")
        print("  fix the clone or the selection rules before continuing.")
    if dry_run:
        print("\n[dry-run] nothing written")
        return 0
    print(f"\n[written] {wrote} new/changed, {unchanged} unchanged -> "
          f"{GROUNDING_DIR.relative_to(WORKSPACE)}/A*.md")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="*", default=[],
                    help="render only these ids")
    args = ap.parse_args()
    return run(args.dry_run, args.only)


if __name__ == "__main__":
    raise SystemExit(main())
