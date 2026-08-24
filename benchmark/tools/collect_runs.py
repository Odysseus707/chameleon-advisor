#!/usr/bin/env python3
"""Collect chatbot answers for the benchmark, with the advisor ON or OFF.

RUNS ON THE NODE. It needs the built vect_store and a live Ollama, so it fails
fast anywhere else rather than half-producing a run.

The point is a single-variable experiment. This reproduces web_rag.py's answer
path exactly -

    context = build_context(question, vectorstore, parents, ...)
    if ADVISOR_ENABLED and advisor_room.should_fire(question, gate):
        context += "\\n\\n=== EDGE RESOURCE ADVISORY ===\\n\\n" + advisor_room.advise(question)
    chain.invoke({question, context, history=[]})

- so the only difference between the two arms is whether the advisor fires. Same
docs RAG, same model, same hardware, same prompts. If this drifts from web_rag,
the arms stop being the deployed system and the comparison is worthless; keep
them in sync.

WHY blind BY DEFAULT. The fed conditions paste whole artifacts into the question.
That would hand the baseline arm the very artifacts the advisor exists to supply,
collapsing the variable under test - and a 39 KB artifact blob as a retrieval
query is not what the deployed chatbot ever sees. Fed conditions are for
paste-driven systems (Sonnet), not for this A/B.

  # on the node, detached, one arm at a time
  setsid nohup ~/.venv/bin/python tools/collect_runs.py \\
      --system s8-qwen32b-noadv --advisor off > ~/collect_noadv.log 2>&1 &

  setsid nohup ~/.venv/bin/python tools/collect_runs.py \\
      --system s9-qwen32b-adv --advisor on  > ~/collect_adv.log 2>&1 &

Resumable: a non-empty answer file is never regenerated, so a dropped SSH
session or an interrupted run costs only the item in flight. Writes only
runs/<condition>/<system>/; never exports/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from provenance import record  # noqa: E402


def die(msg: str):
    raise SystemExit(f"collect_runs: {msg}")


def _call_with_backoff(fn, tries: int = 6, base: float = 3.0):
    """Retry transient rate limits before a failure is allowed to become an answer.

    This module records failures into the answer file on purpose, and the resume
    logic skips any non-empty file. Without this, one 429 from the gateway would
    be frozen into the dataset as though the model had produced it, and every
    later re-run would skip it. Only rate limits are retried; a genuine error
    still fails fast and gets recorded, which is the documented behaviour.
    """
    for i in range(tries):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - SDK error types vary
            msg = str(exc)
            transient = "429" in msg or "ratelimit" in msg.lower().replace(" ", "")
            if not transient or i == tries - 1:
                raise
            wait = base * (2 ** i)
            print(f"    rate limited; retry {i + 1}/{tries - 1} in {wait:.0f}s",
                  flush=True)
            time.sleep(wait)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--system", required=True,
                    help="run directory name, e.g. s9-qwen32b-adv")
    ap.add_argument("--advisor", choices=["on", "off"], required=True)
    ap.add_argument("--conditions", default="blind",
                    help="comma-separated (default: blind - see module docstring)")
    ap.add_argument("--suite", default="all", choices=["all", "core", "reservation"])
    ap.add_argument("--rag-root", type=Path,
                    default=ROOT.parent / "RAG-docs-chameleon")
    ap.add_argument("--gate", type=float,
                    default=float(os.environ.get("ADVISOR_GATE", "1.0")))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be collected, contact nothing")
    args = ap.parse_args()

    import yaml

    # -- which (item, condition) pairs are in scope -------------------------
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    todo = []
    for p in sorted((ROOT / "items").glob("*.yaml")):
        item = yaml.safe_load(p.read_text())
        if args.suite != "all" and item.get("suite", "core") != args.suite:
            continue
        for cond in item.get("fed_sets", {}):
            if cond not in conditions:
                continue
            prompt_file = ROOT / "prompts" / cond / f"{item['id']}.txt"
            if not prompt_file.is_file():
                print(f"  WARN: no prompt file {prompt_file.relative_to(ROOT)}; "
                      "run tools/make_run_prompts.py", file=sys.stderr)
                continue
            out = ROOT / "runs" / cond / args.system / f"{item['id']}.md"
            done = out.is_file() and out.read_text(encoding="utf-8").strip()
            todo.append((item, cond, prompt_file, out, bool(done)))

    pending = [t for t in todo if not t[4]]
    # Count what is genuinely already on disk BEFORE --limit truncates, or a
    # limited smoke test reports itself as a nearly-complete run.
    already = len(todo) - len(pending)
    if args.limit:
        pending = pending[:args.limit]

    print(f"system={args.system}  advisor={args.advisor}  gate={args.gate}")
    print(f"conditions={conditions}  suite={args.suite}")
    print(f"{len(todo)} in scope, {already} already collected, "
          f"{len(pending)} to do"
          + (f" (--limit {args.limit})" if args.limit else ""), flush=True)
    if args.dry_run or not pending:
        for item, cond, _, _, _ in pending[:10]:
            print(f"    would collect {cond}/{item['id']}")
        return 0

    # -- wire up the deployed answer path ----------------------------------
    if not args.rag_root.is_dir():
        die(f"no RAG app at {args.rag_root}. This runs on the node.")
    sys.path.insert(0, str(args.rag_root))
    os.chdir(args.rag_root)          # rag.py resolves VECT_STORE_PATH relatively

    try:
        from rag import (VECT_STORE_PATH, build_context, create_llm_chain,
                         load_parents, load_vectorstore)
    except ImportError as exc:
        die(f"cannot import rag.py ({exc}). Use the RAG venv on the node.")
    if not Path(VECT_STORE_PATH).exists():
        die(f"no vect_store at {VECT_STORE_PATH}; run python build_index.py first")

    room = None
    if args.advisor == "on":
        os.environ["ADVISOR_ENABLED"] = "true"
        import advisor_room
        room = advisor_room
        room.get_room()              # fail now, not 3 hours in
    else:
        os.environ["ADVISOR_ENABLED"] = "false"

    model = os.environ.get("LLM_MODEL", "(default)")
    print(f"model={model}  vect_store={VECT_STORE_PATH}", flush=True)

    vectorstore, parents, chain = (load_vectorstore(), load_parents(),
                                   create_llm_chain())

    meta_path = ROOT / "runs" / conditions[0] / args.system / "_meta.jsonl"
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    ok = err = fired_n = 0
    t_start = time.time()
    for i, (item, cond, prompt_file, out, _) in enumerate(pending, 1):
        question = prompt_file.read_text(encoding="utf-8")
        t0 = time.time()
        fired = False
        try:
            _sources, context, _dbg = build_context(question, vectorstore, parents)
            if room is not None and room.should_fire(question, args.gate):
                fired = True
                context += ("\n\n=== EDGE RESOURCE ADVISORY ===\n\n"
                            + room.advise(question))
            resp = _call_with_backoff(
                lambda: chain.invoke({"question": question, "context": context,
                                      "history": []}))
            text = getattr(resp, "content", None) or str(resp)
            ok += 1
        except Exception as exc:  # a failure is a result; record it, do not hide
            text = (f"COLLECT ERROR: {type(exc).__name__}: {exc}\n\n"
                    + traceback.format_exc(limit=3))
            err += 1
        dt = time.time() - t0
        fired_n += fired

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        # Bind the answer to the exact prompt, so a later item edit cannot
        # silently invalidate it. See tools/provenance.py.
        record(out.parent, item["id"], item["prompt"],
               system=args.system, condition=cond, model=model,
               advisor=args.advisor, advisor_fired=fired,
               seconds=round(dt, 1))
        with meta_path.open("a") as fh:
            fh.write(json.dumps({
                "item": item["id"], "condition": cond, "advisor": args.advisor,
                "advisor_fired": fired, "seconds": round(dt, 1), "model": model,
                "chars": len(text),
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }) + "\n")

        rate = (time.time() - t_start) / i
        print(f"  [{i}/{len(pending)}] {cond}/{item['id']:<5} {dt:6.1f}s "
              f"advisor_fired={fired}  eta {(len(pending) - i) * rate / 60:5.1f}m",
              flush=True)

    print(f"\ndone: {ok} answered, {err} errored, advisor fired on {fired_n}"
          f"/{len(pending)}")
    print(f"elapsed {(time.time() - t_start) / 60:.1f} min -> "
          f"runs/<cond>/{args.system}/")
    if args.advisor == "on" and fired_n == 0:
        print("\nWARNING: the advisor never fired. This arm is identical to the "
              "baseline and the comparison measures nothing. Check --gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
