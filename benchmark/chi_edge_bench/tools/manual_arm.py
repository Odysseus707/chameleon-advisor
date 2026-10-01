#!/usr/bin/env python3
"""manual_arm: a paste-ready arm for a model you drive by hand.

  python tools/manual_arm.py --new s27-claude-noadv --advisor off
  python tools/manual_arm.py --new s28-claude-adv   --advisor on
  python tools/manual_arm.py --new s33-claude-artifacts --advisor artifacts
  python tools/manual_arm.py --status s27-claude-noadv
  python tools/manual_arm.py --prepare s27-claude-noadv     # before scoring

`--advisor artifacts` is NOT the advisor arm above. It wraps each item's
prompt with its item.fed_sets.matched artifacts (grounding docs pinned at
corpus-build time), the same fixed-pack mechanism the edge wing's
make_run_prompts.py uses for its `matched` condition - not the live
RouterTree retrieval that `--advisor on` falls back to for site-less items.
An item with no matched artifacts (every RB item, and any CB item the corpus
did not pin one for) gets the bare prompt, same as blind.

Every item's prompt is ALSO written standalone to `prompts/<ITEM>.md` inside
the arm folder - PROMPTS.md is the read-in-order pack (system prompt once,
then every item with its answer filename), `prompts/<ITEM>.md` is the
copy-one-item file when you already know which item you want, e.g. CB14.

WHY THIS EXISTS
Some models are worth measuring and too expensive to call 96 times over an API.
Those get answered in a chat window and pasted in. Both earlier hand-driven
arms - s1-chatbot and s2-sonnet - were assembled that way by hand, and that is
where two problems came from that this tool removes.

PROBLEM 1: THE PROMPT DRIFTS.
An arm is only comparable to the API arms if the model saw the SAME system
prompt and the SAME item prompt. Retyping either invalidates the comparison
silently. So the prompt pack is generated from `run_llm_wing.SYSTEM_PROMPT` and
the items themselves, never transcribed - if the API arms' prompt changes, a
regenerated pack changes with it.

PROBLEM 2: A BLANK ANSWER SCORES AS A WRONG ANSWER.
`score_wing.py` skips an item whose `.md` is MISSING and reports it as missing,
but an EMPTY `.md` is read, extracts no code, and scores as a failure. Pre-made
blanks are exactly what a paste-in workflow needs and exactly what silently
turns "not answered yet" into "answered badly". `--prepare` moves every still-
empty file into `_unanswered/` so a partly-finished arm scores honestly over
what was actually answered.

ON PASTING WITHOUT ``` FENCES
Chat answers pasted by hand rarely carry code fences, and the harness extracts
nothing from that shape - which is why the two historical hand-driven arms
scored far below what they had actually written (matched/s1-chatbot: 2/47, and
9/47 once the code was readable). So paste raw chat output verbatim; do not
tidy it and do not add fences it did not have.

`--prepare` makes it readable, HERE rather than in the harness. Recovering
unfenced code inside `runner.extract_code` was tried and reverted: it moved 79
stored verdicts, every one of them in those two hand-pasted arms, which failed
Level 2 verdict parity. An extraction improvement must not restate a past
measurement (R1). Normalising at ingest reaches only the arm being prepared.

What `--prepare` does to an answer is additive and reversible: the original
paste is copied to `_raw/<ITEM>.md` and left untouched in place, and a fenced
copy of the recovered code is APPENDED. Nothing is removed, so the prose the
ranked-list checkers read is exactly as pasted, and the code the AST checkers
read is now findable.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from chi_edge_bench.paths import items_dir, runs_dir, wing_data   # noqa: E402


#: Lines that begin a run of Python in prose. Deliberately narrow - a heading
#: like "Reserve the node:" must not open a code block, and a prose line
#: mentioning `chi.use_site` must not either.
_CODE_START = re.compile(
    r"^\s*(?:from\s+\w|import\s+\w|@\w|def\s+\w|class\s+\w|with\s+\w|for\s+\w|"
    r"if\s+\w|try:|while\s+\w|print\(|[A-Za-z_][\w.]*\s*=\s*\S|"
    r"[A-Za-z_][\w.]*\s*\()")


def unfenced_blocks(text: str) -> str:
    """Recover Python from an answer that was pasted without ``` fences.

    A model answering in a chat window writes prose around its code, and the
    person pasting it rarely adds fences. The two paths above cannot read that:
    there are no fences, and the whole text does not parse because the prose is
    not Python. The answer then extracts as the empty string and scores as
    though no code was written at all - which measures the paste, not the model.

    Method: take every maximal run of consecutive non-blank lines that starts
    with something only code starts with, and keep the run if `ast.parse`
    accepts it. Parsing is what makes this safe rather than a guess - a prose
    line that happens to match the pattern is discarded when the block it opens
    fails to parse, so the failure mode is dropping code, never inventing it.

    STRICTLY ADDITIVE. It runs only when the fenced path found nothing AND the
    whole-text path failed, so every answer that previously yielded code yields
    exactly the same code. Verified against the existing arms, whose scores must
    not move because extraction got better.
    """
    import ast
    out, buf = [], []
    depth = 0

    def flush():
        if not buf:
            return
        block = "\n".join(buf)
        try:
            ast.parse(block)
        except SyntaxError:
            return
        out.append(block)

    def delta(s: str) -> int:
        return sum(s.count(c) for c in "([{") - sum(s.count(c) for c in ")]}")

    for line in text.splitlines():
        # An open bracket makes the NEXT line a continuation whatever it looks
        # like. Without this, the closing ")" of a multi-line call matches no
        # start pattern, the block is flushed before its own bracket closes,
        # and the whole call is dropped for failing to parse - which silently
        # discarded the Server(...) construction, and with it the image name
        # and the reservation wiring, in the first version of this function.
        if depth > 0:
            buf.append(line)
            depth += delta(line)
            continue
        if not line.strip():
            flush()
            buf.clear()
            continue
        if buf and (line.startswith((" ", "\t")) or _CODE_START.match(line)):
            buf.append(line)
        elif _CODE_START.match(line):
            flush()
            buf.clear()
            buf.append(line)
        else:
            flush()
            buf.clear()
            continue
        depth += delta(line)
    flush()
    return "\n\n".join(out)


def load_items(wing: str, prefix: str) -> list[dict]:
    d = wing_data(wing) / "items" if wing else items_dir()
    return [yaml.safe_load(p.read_text(encoding="utf-8"))
            for p in sorted(d.glob(f"{prefix}*.yaml"))]


#: Same wrapper text as the edge wing's make_run_prompts.build_fed, so a
#: matched-artifacts prompt is recognisable as the same kind of thing whether
#: it was built for CHI@Edge or for the Chameleon wing.
_FED_INTRO = ("Here is reference material about Chameleon Cloud that may be "
              "relevant to my question.")
_FED_OPEN = "=== REFERENCE MATERIAL ==="
_FED_CLOSE = "=== END REFERENCE MATERIAL ==="


def build_fed(prompt: str, artifacts: list[str], grounding_dir: Path) -> str:
    """Wrap `prompt` with its fed_sets.matched artifacts as reference material.

    Mirrors chi_edge_bench.tools.make_run_prompts.build_fed exactly (intro,
    concatenated grounding docs, question) so the matched condition means the
    same thing on both wings.
    """
    material = "\n\n".join(
        (grounding_dir / f"{a}.md").read_text(encoding="utf-8") for a in artifacts
    )
    return "\n".join([_FED_INTRO, _FED_OPEN, material, _FED_CLOSE, "",
                      "Question: " + prompt])


def advisor_finding(item: dict) -> str:
    """The same finding the advisor arm would supply, or a reason why not."""
    try:
        import run_llm_wing as W
        W._attach_advisor()
        return W.advisor_finding(item)          # type: ignore[attr-defined]
    except Exception as exc:                    # noqa: BLE001
        return f"[advisor finding unavailable: {type(exc).__name__}: {exc}]"


def build(arm: str, condition: str, wing: str, prefix: str, advisor: str) -> Path:
    import run_llm_wing as W
    from chi_edge_bench import paths
    # The wing is process-global state and the advisor resolves this item's
    # snapshot through it (`snapshot_now(item["snapshot"])`). Without this the
    # chameleon snapshots are looked for under the EDGE wing's data directory,
    # every finding comes back as a FileNotFoundError string, and the pack
    # still LOOKS complete - 96 prompts, each carrying an error where the
    # advisor's answer should be. run_llm_wing.py:201 sets it for the same
    # reason.
    paths.set_wing(wing)
    items = load_items(wing, prefix)
    if not items:
        raise SystemExit(f"no {prefix}* items found for wing {wing!r}")
    out = runs_dir() / condition / arm
    out.mkdir(parents=True, exist_ok=True)
    # One prompt per file, same folder as the blank answers - PROMPTS.md below
    # is a read-in-order reference pack, this is the copy-one-item source. Its
    # own subfolder because `<ITEM>.md` in `out` is already claimed by the
    # (initially blank) answer file; the two must not collide.
    prompts_subdir = out / "prompts"
    prompts_subdir.mkdir(exist_ok=True)

    label = {"off": "off", "on": "on",
             "artifacts": "off (fed matched artifacts instead)"}[advisor]
    L = [f"# Prompt pack - {arm}\n",
         f"{len(items)} items | advisor **{label}** | wing `{wing}` | "
         f"condition `{condition}`\n",
         "## How to use this\n",
         "1. Start a fresh chat. Paste the **system prompt** below once, as the "
         "first message (or set it as the system / custom instruction).\n"
         "2. For each item, copy its prompt from `prompts/<ITEM>.md` (or the "
         "matching section below) as a new user message. Use a NEW chat per "
         "item if you can - carrying context between items is not what the "
         "API arms do, so it would not be the same measurement.\n"
         "3. Paste the model's reply verbatim into the matching `<ITEM>.md` in "
         "this folder (NOT `prompts/<ITEM>.md` - that one holds the prompt, "
         "not the answer). **Do not add code fences, reformat, or trim it.** "
         "The harness reads unfenced code correctly.\n"
         "4. When done, or part-done, run:\n"
         f"   `python tools/manual_arm.py --prepare {arm}`\n"
         f"   then `python tools/score_wing.py --system {arm}`\n",
         "## System prompt - paste once, verbatim\n",
         "```text", W.SYSTEM_PROMPT, "```\n",
         "---\n"]

    grounding_dir = wing_data(wing) / "grounding"
    fed_count = 0
    for it in items:
        L.append(f"## {it['id']}\n")
        L.append(f"Paste the reply into `{it['id']}.md`\n")
        body = it["prompt"]
        if advisor == "on":
            body = W.ADVISOR_PREAMBLE.format(finding=advisor_finding(it)) + body
        elif advisor == "artifacts":
            matched = ((it.get("fed_sets") or {}).get("matched")) or []
            if matched:
                body = build_fed(body, matched, grounding_dir)
                fed_count += 1
        L.append("```text")
        L.append(body)
        L.append("```\n")
        (prompts_subdir / f"{it['id']}.md").write_text(body, encoding="utf-8")
        f = out / f"{it['id']}.md"
        if not f.exists():
            f.write_text("")

    (out / "PROMPTS.md").write_text("\n".join(L) + "\n")
    print(f"  {len(items)} individual prompt file(s) under {prompts_subdir}/")
    if advisor == "artifacts":
        print(f"  fed matched artifacts to {fed_count}/{len(items)} item(s); "
              f"the rest got the bare prompt (empty fed_sets.matched)")
    return out


def status(path: Path) -> tuple[int, int, list[str]]:
    files = sorted(p for p in path.glob("*.md") if p.name != "PROMPTS.md")
    empty = [p.stem for p in files if not p.read_text().strip()]
    return len(files) - len(empty), len(files), empty


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--new", metavar="ARM")
    g.add_argument("--status", metavar="ARM")
    g.add_argument("--prepare", metavar="ARM",
                   help="move still-empty answers into _unanswered/ so the "
                        "scorer counts them as missing, not failed")
    ap.add_argument("--advisor", default="off",
                    choices=["on", "off", "artifacts"])
    ap.add_argument("--condition", default="")
    ap.add_argument("--wing", default="chameleon_bench")
    ap.add_argument("--suite", default="all",
                    help="which items to include. Same vocabulary as "
                         "score_wing and run_llm_wing, and the same default: "
                         "the whole wing. A manual arm that covers less than "
                         "the arm it is compared against is not a comparison.")
    args = ap.parse_args()

    from chi_edge_bench.tools.score_wing import SUITES
    prefix = SUITES.get(args.wing, {}).get(args.suite)
    if prefix is None:
        raise SystemExit(f"unknown suite {args.suite!r} for wing {args.wing!r}; "
                         f"try {sorted(SUITES.get(args.wing, {}))}")
    #: Suite -> the run directory a reader would expect, matching run_llm_wing.
    if not args.condition:
        args.condition = {"all": "chameleon_wing",
                          "reservation": "baremetal_reservation",
                          "core": "baremetal_core"}.get(args.suite, args.suite)

    arm = args.new or args.status or args.prepare
    path = runs_dir() / args.condition / arm

    if args.new:
        out = build(arm, args.condition, args.wing, prefix, args.advisor)
        _, total, _ = status(out)
        print(f"created {out}")
        print(f"  {total} empty answer file(s) + PROMPTS.md")
        print(f"  advisor={args.advisor}; prompts generated from "
              "run_llm_wing.SYSTEM_PROMPT, not transcribed")
        return 0

    if not path.is_dir():
        raise SystemExit(f"no such arm: {path}")

    filled, total, empty = status(path)
    if args.status:
        print(f"{arm}: {filled}/{total} answered")
        if empty:
            print("  still empty: " + ", ".join(empty[:20])
                  + (f" ... (+{len(empty) - 20})" if len(empty) > 20 else ""))
        return 0

    park = path / "_unanswered"
    if empty:
        park.mkdir(exist_ok=True)
        for stem in empty:
            (path / f"{stem}.md").rename(park / f"{stem}.md")
        print(f"{arm}: moved {len(empty)} unanswered item(s) into {park.name}/ "
              "- scoring reports them MISSING rather than failed")

    import ast
    raw = path / "_raw"
    fenced = 0
    for f in sorted(path.glob("*.md")):
        if f.name == "PROMPTS.md":
            continue
        text = f.read_text(encoding="utf-8")
        if not text.strip() or "```" in text:
            continue                      # already readable; leave it alone
        try:
            ast.parse(text)
            continue                      # whole answer is code; already fine
        except SyntaxError:
            pass
        code = unfenced_blocks(text)
        if not code.strip():
            continue                      # no code in it; a prose answer
        raw.mkdir(exist_ok=True)
        shutil.copy2(f, raw / f.name)
        f.write_text(text.rstrip() + "\n\n```python\n" + code + "\n```\n",
                     encoding="utf-8")
        fenced += 1
    if fenced:
        print(f"{arm}: fenced the recovered code in {fenced} answer(s); "
              f"originals copied to _raw/")

    # Bind each pasted answer to the prompt it answered. The API arms record
    # this at collection time; a paste arm has no collection moment, so until
    # now its cells were never manifested at all and `provenance.py --check`
    # reported every one of them as unmanifested forever. --prepare is the
    # "I am done pasting" step, which is the only honest place to stamp it.
    #
    # provenance=recorded is right here: the prompt hashed is the one in the
    # item bank NOW, and --prepare runs against the same bank the answer was
    # copied out of. It cannot prove the paste happened before a later item
    # edit - but neither can it silently pass one, because a subsequent edit
    # moves the hash and --check reports the drift.
    from chi_edge_bench.tools import provenance
    items = {i["id"]: i for i in load_items(args.wing, "")}
    stamped = 0
    for f in sorted(path.glob("*.md")):
        if f.name == "PROMPTS.md" or not f.read_text(encoding="utf-8").strip():
            continue
        item = items.get(f.stem)
        if item is None:
            continue
        provenance.record(path, item["id"], item["prompt"],
                          system=arm, condition=args.condition, wing=args.wing,
                          advisor=args.advisor, produced_by="manual-paste")
        stamped += 1
    if stamped:
        print(f"  recorded provenance for {stamped} pasted answer(s)")

    print(f"  {filled} answered item(s) ready to score")
    return 0


if __name__ == "__main__":
    sys.exit(main())
