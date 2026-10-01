#!/usr/bin/env python3
"""run_llm_wing: answer a wing's items with an LLM, with or without the advisor.

The A/B this exists for. Both arms send the SAME item prompt to the SAME model
with the SAME system prompt; the only difference is whether the advisor's
finding is supplied as context first:

  --advisor off   prompt -> model -> answer
  --advisor on    prompt + the ladder's finding -> model -> answer

So a difference in score is attributable to the advisor's contribution and to
nothing else. Anything else that varied between the two would make the
comparison unreadable, which is why the system prompt is a constant here rather
than being tuned per arm.

The model is pinned by tools/bench_config.yaml (fork.env), applied with
setdefault so an exported environment still wins. The API key is read from the
environment and is never written to a file, a manifest, or this program's
output.

  # both arms over the 32 reservation items
  python tools/run_llm_wing.py --advisor off --system s19-tejas-noadv
  python tools/run_llm_wing.py --advisor on  --system s20-tejas-adv

  # then
  python tools/score_wing.py --system s19-tejas-noadv --compare s20-tejas-adv
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent

#: Identical for both arms, on purpose. The advisor arm's advantage must come
#: from the context it is given, not from a differently-worded instruction.
#: Note the format clause. Left implicit, the model answered in JSON, and the
#: scorer's rank-line pattern requires a line to BEGIN with "1." or "-" - so a
#: perfectly correct ranked list wrapped in JSON extracted as zero node types
#: and scored zero. That is a measurement artefact, not a model failure, and it
#: made a correct advisor arm look identical to a hallucinating bare one. The
#: instruction is identical for both arms, so it constrains the shape of the
#: answer without touching the content either arm is able to produce.
SYSTEM_PROMPT = (
    "You are a Chameleon testbed assistant. Answer the user's question about "
    "reserving and using Chameleon hardware. Be concrete and specific. When "
    "nothing can satisfy the request, say so plainly rather than recommending "
    "something that does not fit.\n\n"
    "Format: reply in plain text or Markdown, never JSON. When asked for a "
    "ranked list, write each option on its own line beginning with its number "
    "and a period, like:\n"
    "1. <node_type> - <one line of justification>\n"
    "2. <node_type> - <one line of justification>\n"
    "Use the exact node type identifier, not a marketing name for the hardware."
)

ADVISOR_PREAMBLE = (
    "The resource advisor examined live availability and the hardware "
    "capability table for this site and reported the following. Treat it as "
    "the authoritative account of what exists and what is free; it is derived "
    "from measurements, not from recollection.\n\n"
    "--- advisor finding ---\n{finding}\n--- end advisor finding ---\n\n"
)


ARTIFACT_PREAMBLE = (
    "The resource advisor retrieved the following reference material from the "
    "Chameleon artifact corpus for this question. It is real code from real "
    "notebooks on this testbed; prefer its idioms over recollection.\n\n"
    "--- retrieved reference material ---\n{context}\n"
    "--- end reference material ---\n\n"
)

_ROUTER = None


def artifact_context(item: dict) -> str | None:
    """Retrieved artifact grounding for an item the availability ladder cannot answer.

    THE ADVISOR HAS TWO HALVES AND ONLY ONE WAS EVER WIRED IN HERE. The ladder
    answers "what is free at this site" and needs a site; the retrieval router
    answers "what does the corpus show about doing this" and needs only the
    question. CB items ask for CODE and carry no site, so `advisor_finding`
    returns None for all 40 - and until now that meant the advisor arm sent
    them a prompt byte-identical to the bare arm's. Both arms scored 0.0% on
    mechanism and 0.8% on specifics, which measured a model answering code
    questions with no reference material at all: 26 of 40 replied with portal
    click-throughs and 10 with `openstack` CLI.

    RouterTree, not the flat router: 35.0% vs 22.5% L2 recall on this wing's
    own items, and the tree is what the pipeline runs (D45).
    """
    global _ROUTER
    if item.get("site") and item.get("snapshot"):
        return None                       # the ladder speaks for these
    _attach_advisor()
    if _ROUTER is None:
        from advisor.artifacts.store import ArtifactStore
        from advisor.artifacts.tree import RouterTree
        _ROUTER = RouterTree(ArtifactStore().build())
    result = _ROUTER.route(item["prompt"])
    text = (result.context_text or "").strip()
    return text or None


def _attach_advisor() -> None:
    """Make the `advisor` package importable, saying so if it came from source."""
    try:
        import advisor  # noqa: F401
        return
    except ImportError:
        pass
    from chi_edge_bench.paths import workspace
    sibling = workspace().parent / "chi-edge-advisor"
    if not sibling.is_dir():
        raise SystemExit(f"the `advisor` package is not importable and no "
                         f"sibling chi-edge-advisor/ exists at {sibling}")
    print(f"[run_llm_wing] using uninstalled advisor at {sibling}",
          file=sys.stderr)
    sys.path.insert(0, str(sibling))


def pin_model_env(config_path: Path) -> dict:
    """Apply the benchmark's pinned model settings, without overriding exports.

    Returned for the manifest so a collected arm records which model produced
    it. A number is only interpretable next to the model that generated it.
    """
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        env = (cfg.get("fork") or {}).get("env") or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"[run_llm_wing] no pinned model config ({exc})", file=sys.stderr)
        env = {}
    for key, value in env.items():
        os.environ.setdefault(key, str(value))
    return {"base": os.environ.get("LLM_API_BASE") or os.environ.get("TEJAS_BASE_URL"),
            "model": os.environ.get("LLM_MODEL") or os.environ.get("TEJAS_MODEL"),
            "provider": os.environ.get("LLM_PROVIDER")}


def advisor_finding(item: dict) -> str | None:
    """The ladder's answer for this item, or None when the item has no site.

    The advisor answers "what is free at this site right now, and what of it
    fits". A CB item asks for CODE - reserve this node type, boot this image -
    and carries no `site` or `snapshot` at the top level to answer it against;
    all 40 of them would raise KeyError here. Returning None instead means the
    A/B stays honest: those items get the SAME prompt in both arms, so their
    scores are identical by construction and any difference between the arms is
    attributable to the items that actually received context. Inventing a site
    for them, or skipping them, would both make the comparison say more than
    the data supports.
    """
    if not item.get("site") or not item.get("snapshot"):
        return None
    _attach_advisor()
    from advisor.inventory.catalog import capability_table_types
    from advisor.select.ladder import Request, select
    from chi_edge_bench.tools.run_advisor import (chameleon_availability,
                                                  render_chameleon,
                                                  snapshot_now)

    availability = chameleon_availability(item)
    result = select(capability_table_types(), availability, Request(
        site=item["site"], count=item.get("requested_count", 1),
        hours=item.get("requested_hours", 3),
        requires=item.get("requires") or {}, api_family="baremetal",
        now=snapshot_now(item["snapshot"])))
    return render_chameleon(result, item["snapshot"],
                            count=item.get("requested_count", 1))


class PlainClient:
    """A chat completion with NO forced response format.

    Deliberately not advisor.reason.llm.TejasClient. That one hardcodes
    response_format={"type": "json_object"}, which is right for its own caller -
    the Reasoner parses JSON into a Recommendation - and wrong here in a way
    that quietly corrupted the measurement:

      * the gateway made every benchmark answer JSON, so the scorer's rank-line
        pattern (which needs a line to BEGIN "1.") extracted zero node types
        from answers that were correct, and both arms scored 0/32;
      * once the system prompt asked for Markdown, the model complied and the
        gateway rejected its own model's output with a 400, "Model did not
        output valid JSON".

    So the benchmark asks the model the way a user would, and the advisor keeps
    the client its own parsing depends on.
    """

    def __init__(self):
        from openai import OpenAI
        from advisor.config import settings

        self.model = settings.tejas_model
        self.name = "tejas-plain"
        self._client = OpenAI(base_url=settings.tejas_base_url,
                              api_key=settings.tejas_api_key or "not-needed")

    def complete(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.1,
            max_tokens=800,
        )
        return resp.choices[0].message.content or ""


def ask(client, system: str, user: str, retries: int = 3) -> str:
    """One completion, with backoff. A refusal to answer is not an answer."""
    last = None
    for attempt in range(retries):
        try:
            return client.complete(system, user)
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"model unreachable after {retries} attempts: {last}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--wing", default="chameleon_bench")
    ap.add_argument("--suite", default="all",
                    help="which items to answer. Default is the WHOLE wing - "
                         "an arm that silently covered only part of the "
                         "benchmark is the more expensive mistake. Suite names "
                         "are score_wing's, so the two tools cannot disagree "
                         "about what a suite contains.")
    ap.add_argument("--advisor", default="off", choices=["on", "off"])
    ap.add_argument("--system", default="", help="run directory name")
    ap.add_argument("--condition", default="",
                    help="run directory under runs/. Defaults to match the "
                         "suite, so a full-wing arm does not land in a folder "
                         "named for the reservation items alone - the folder "
                         "name is what a reader takes the arm's scope to be.")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--config", default=str(HERE / "bench_config.yaml"))
    ap.add_argument("--overwrite", action="store_true",
                    help="re-answer items that already have a non-empty file")
    ap.add_argument("--dry-run", action="store_true",
                    help="build the prompts and report, contacting no model")
    args = ap.parse_args()

    from chi_edge_bench import paths
    from chi_edge_bench.tools import provenance

    # P2: the wing is process state; a run that forgets it collects answers
    # against the wrong wing's snapshots and grades them against the wrong
    # hardware. Set explicitly, including for the default.
    paths.set_wing(args.wing)

    #: Suite -> the run directory a reader would expect to find it in.
    CONDITION_FOR = {"all": "chameleon_wing",
                     "reservation": "baremetal_reservation",
                     "core": "baremetal_core"}
    if not args.condition:
        args.condition = CONDITION_FOR.get(args.suite, args.suite)

    pinned = pin_model_env(Path(args.config))
    system_name = args.system or f"tejas-{'adv' if args.advisor == 'on' else 'noadv'}"

    from chi_edge_bench.tools.score_wing import SUITES
    prefix = SUITES.get(args.wing, {}).get(args.suite)
    if prefix is None:
        print(f"ERROR: unknown suite {args.suite!r} for wing {args.wing!r}; "
              f"try {sorted(SUITES.get(args.wing, {}))}", file=sys.stderr)
        return 2
    items = sorted(paths.items_dir().glob(f"{prefix}*.yaml"))
    if args.limit:
        items = items[:args.limit]
    if not items:
        # P5: an empty result set reads as a pass. An arm with no answers in it
        # is not an arm, and it is exactly what a mis-set wing looks like.
        print(f"ERROR: no {prefix}* items under {paths.items_dir()}",
              file=sys.stderr)
        return 2

    print(f"wing={args.wing} suite={args.suite} advisor={args.advisor} items={len(items)}")
    print(f"model={pinned['model']} via {pinned['base']}")

    client = None
    if not args.dry_run:
        _attach_advisor()
        from advisor.config import settings
        if not settings.tejas_api_key:
            print("ERROR: no API key. Export it first:\n"
                  "  set -a; . ~/Documents/SECRET-KEY.txt; set +a",
                  file=sys.stderr)
            return 2
        client = PlainClient()

    outdir = paths.runs_dir() / args.condition / system_name
    outdir.mkdir(parents=True, exist_ok=True)

    ok = err = skipped = no_context = retrieved = 0
    for path in items:
        item = yaml.safe_load(path.read_text(encoding="utf-8"))
        dest = outdir / f"{item['id']}.md"
        if dest.is_file() and dest.read_text().strip() and not args.overwrite:
            skipped += 1
            continue

        user = item["prompt"]
        if args.advisor == "on":
            finding = advisor_finding(item)
            if finding is not None:
                user = ADVISOR_PREAMBLE.format(finding=finding) + user
            else:
                # No site to rank availability against - so ask the advisor's
                # OTHER half. An item the ladder cannot speak to is not an item
                # the advisor has nothing to say about.
                context = artifact_context(item)
                if context is None:
                    no_context += 1
                else:
                    user = ARTIFACT_PREAMBLE.format(context=context) + user
                    retrieved += 1

        if args.dry_run:
            print(f"  {item['id']}: {len(user)} chars of prompt")
            ok += 1
            continue

        try:
            text = ask(client, SYSTEM_PROMPT, user)
            ok += 1
        except Exception as exc:  # a crash is a result: record it, do not hide it
            text = (f"LLM ERROR: {type(exc).__name__}: {exc}\n\n"
                    + traceback.format_exc(limit=3))
            err += 1
        # Verbatim. Fences intact, prose intact - the scorer reads what the
        # model actually said, not a cleaned-up version of it.
        dest.write_text(text)
        provenance.record(outdir, item["id"], item["prompt"],
                          system=system_name, condition=args.condition,
                          wing=args.wing, advisor=args.advisor,
                          produced_by=pinned["provider"] or "llm",
                          model=pinned["model"],
                          availability_mode="snapshot")
        print(f"  {item['id']}: {len(text)} chars")

    print(f"\n{len(items)} items -> {outdir}")
    print(f"  answered {ok}   errored {err}   skipped {skipped}")
    if args.advisor == "on":
        # Which half of the advisor spoke, per item. A silent arm that supplied
        # nothing to 40 of 136 items is what this line exists to make visible.
        ladder = len(items) - retrieved - no_context
        print(f"  advisor context: ladder {ladder}, retrieved artifacts "
              f"{retrieved}, NONE {no_context}")
    if not args.dry_run:
        print(f"\nScore with:\n  python tools/score_wing.py --wing {args.wing} "
              f"--system {system_name}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
