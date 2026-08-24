"""chi-edge-bench: one entry point for the CHI@Edge coding benchmark.

Four ways to get answers to score, in increasing order of setup cost:

  1. drop-in     `prompts`, answer the .txt files however you like, `score-runs`.
                 No key, no network, no SDK - only PyYAML.
  2. openai      any /v1/chat/completions endpoint: OpenAI, a local Ollama or
                 vLLM, a LiteLLM gateway. `collect --adapter openai --base-url`.
  3. anthropic   Claude models. `collect --adapter anthropic`.
  4. fork        the full RAG + advisor pipeline, needs the extra deps and a
                 built vectorstore. `collect --adapter fork --advisor on|off`.

Every subcommand reads the benchmark from the installed package and writes to a
workspace outside it; `chi-edge-bench where` prints both.
"""
from __future__ import annotations

import argparse
import sys

from chi_edge_bench import __version__, paths


# -- helpers ---------------------------------------------------------------

def _delegate(module_name: str, argv: list[str]) -> int:
    """Run a tool's own main() with argv, so the CLI never forks its logic.

    The tools are argparse scripts that read sys.argv; handing them a spliced
    argv keeps every flag they document working, and keeps this file from
    becoming a second, drifting definition of what they accept.
    """
    import importlib
    saved = sys.argv
    sys.argv = [module_name.rsplit(".", 1)[-1], *argv]
    try:
        # Import under the spliced argv too: export_xlsx and friends do work at
        # module level rather than in a main().
        mod = importlib.import_module(module_name)
        rc = mod.main() if hasattr(mod, "main") else 0
    except ImportError as exc:           # an ungated optional extra
        raise SystemExit(str(exc)) from exc
    except SystemExit as exc:            # argparse and the tools both use this
        rc = exc.code
    finally:
        sys.argv = saved
    if rc is None:
        return 0
    if isinstance(rc, int):
        return rc
    # SystemExit("message"): the tools raise these for user errors, and the
    # message is the whole point - printing it beats int()-ing it into a crash.
    print(rc, file=sys.stderr)
    return 1


def _iter_items(suite: str):
    import yaml
    for p in sorted(paths.items_dir().glob("*.yaml")):
        item = yaml.safe_load(p.read_text())
        # Items predating the reservation suite carry no `suite` key.
        if suite != "all" and item.get("suite", "core") != suite:
            continue
        yield item


# -- subcommands -----------------------------------------------------------

def cmd_where(args) -> int:
    print(f"benchmark data  {paths.DATA}")
    print(f"  items         {len(list(paths.items_dir().glob('*.yaml')))}")
    print(f"  snapshots     {len(list(paths.snapshots_dir().glob('*.json')))}")
    print(f"  grounding     {len(list(paths.grounding_dir().glob('*.md')))}")
    print(f"workspace       {paths.workspace()}")
    print(f"  chosen by     {paths.workspace_source()}")
    for name, d in (("runs", paths.runs_dir()), ("exports", paths.exports_dir()),
                    ("prompts", paths.prompts_dir())):
        n = sum(1 for _ in d.rglob("*")) if d.is_dir() else 0
        print(f"  {name:<12}  {'exists' if d.is_dir() else 'absent':<7} {n:>6} entries")
    return 0


def cmd_items(args) -> int:
    rows = list(_iter_items(args.suite))
    for item in rows:
        conds = ",".join(item.get("fed_sets", {})) or "-"
        print(f"{item['id']:<6} {item.get('suite', 'core'):<12} "
              f"{item.get('verification_level', 'V0'):<3} {conds}")
    print(f"\n[{len(rows)} items, suite={args.suite}]")
    return 0


def cmd_selftest(args) -> int:
    """The install gate: every gold must pass 100% of its own checkers.

    This is the benchmark's own admission rule (decision D06), so a clean run
    proves the shipped items, checkers, capability table and snapshots are all
    present and mutually consistent. No network, no key, no model.
    """
    argv = ["--suite", args.suite, *args.ids]
    rc = _delegate("chi_edge_bench.harness.validate_golds", argv)
    if rc != 0 or args.golds_only:
        return rc
    print("\n" + "-" * 60)
    return _delegate("chi_edge_bench.harness.tier_assign", ["--suite", args.suite])


def cmd_prompts(args) -> int:
    return _delegate("chi_edge_bench.tools.make_run_prompts", args.rest)


def cmd_score(args) -> int:
    item = paths.items_dir() / f"{args.item}.yaml"
    if not item.is_file():
        raise SystemExit(f"no such item {args.item!r} (see `chi-edge-bench items`)")
    argv = ["--item", str(item)]
    argv += ["--gold"] if args.gold else ["--answer", args.answer]
    if args.snapshot:
        argv += ["--snapshot", args.snapshot]
    return _delegate("chi_edge_bench.harness.runner", argv)


def cmd_score_runs(args) -> int:
    return _delegate("chi_edge_bench.tools.score_runs", args.rest)


def cmd_collect(args) -> int:
    if args.adapter == "fork":
        # The fork path is a different program: it drives the RAG app in-process
        # rather than sending one prompt per request.
        return _delegate("chi_edge_bench.tools.collect_runs", args.rest)
    return _delegate("chi_edge_bench.tools.run_bench",
                     ["--adapter", args.adapter, *args.rest])


def cmd_report(args) -> int:
    return _delegate("chi_edge_bench.tools.report_results", args.rest)


def cmd_compare(args) -> int:
    return _report_against_baseline(args.rest)


def cmd_provenance(args) -> int:
    return _delegate("chi_edge_bench.tools.provenance", args.rest or ["--check"])


# -- baseline comparison ---------------------------------------------------

GROUPS = ("mechanism", "specifics", "safety", "feasibility", "capability")


def _group_rates(rows):
    out = {}
    for g in GROUPS:
        p = sum(int(r.get(f"{g}_passed") or 0) for r in rows)
        t = sum(int(r.get(f"{g}_total") or 0) for r in rows)
        if t:
            out[g] = (p, t)
    return out


def _load_csv(path):
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _report_against_baseline(rest: list[str]) -> int:
    """Put the user's arm next to the shipped reference arms.

    Without this a stranger can score their model but has no yardstick, which
    is most of the value of a benchmark.
    """
    ap = argparse.ArgumentParser(prog="chi-edge-bench report --compare-baseline")
    ap.add_argument("--csv", default=str(paths.exports_dir() / "run_scores.csv"),
                    help="your scored run (default: the last score-runs output)")
    ap.add_argument("--condition", default="blind")
    args = ap.parse_args(rest)

    ref = paths.baselines_dir() / "isolation_scores.csv"
    if not ref.is_file():
        raise SystemExit(f"no shipped baseline at {ref}")

    cols = []
    for row_set, label in _baseline_columns(ref, args.condition):
        cols.append((label, _group_rates(row_set)))

    mine = [r for r in _load_csv(args.csv) if r.get("condition") == args.condition]
    if not mine:
        raise SystemExit(f"no rows for condition={args.condition!r} in {args.csv}")
    for system in sorted({r["system"] for r in mine}):
        rows = [r for r in mine if r["system"] == system]
        cols.append((f"{system} (yours)", _group_rates(rows)))

    # One fixed-width column per arm, labels wrapped onto two header rows, so a
    # long system name cannot stretch the table past a terminal.
    w = 21
    def cell(text):
        return text[:w - 1].rjust(w)

    print(f"condition = {args.condition}\n")
    tops, bots = [], []
    for label, _ in cols:
        head, _, tail = label.partition(" (")
        tops.append(cell(head))
        bots.append(cell(f"({tail}" if tail else ""))
    print(" " * 13 + "".join(tops))
    if any(b.strip() for b in bots):
        print(" " * 13 + "".join(bots))
    print("-" * (13 + w * len(cols)))
    for g in GROUPS:
        if not any(g in d for _, d in cols):
            continue
        line = g.ljust(13)
        for _, d in cols:
            if g in d:
                passed, total = d[g]
                line += cell(f"{100.0 * passed / total:.1f}%  ({passed}/{total})")
            else:
                line += cell("-")
        print(line)
    print("\nReference arms are Meta-Llama-3.3-70B-Instruct via the TACC Tejas\n"
          "gateway; see data/baselines/baselines_summary.md for what they are\n"
          "and are not comparable to.")
    return 0


def _baseline_columns(ref, condition):
    rows = [r for r in _load_csv(ref) if r.get("condition") == condition]
    labels = {
        "s10-llama70b-tejas-noadv": "70B, advisor OFF",
        "s11-llama70b-heuristic-adv": "70B + heuristic adv",
        "s10-llama70b-tejas-adv": "70B + 70B adv",
    }
    for system, label in labels.items():
        sub = [r for r in rows if r["system"] == system]
        if sub:
            yield sub, label


# -- parser ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="chi-edge-bench",
        description=__doc__.splitlines()[0],
        epilog="`chi-edge-bench where` shows which data and workspace are in use.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version",
                    version=f"chi-edge-bench {__version__}")
    ap.add_argument("--workspace", default=None,
                    help="writable root for runs/, exports/ and prompts/ "
                         "(default: nearest .chi-edge-bench marker, else "
                         "./chi-edge-bench-work)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("where", help="show the data and workspace in use")
    p.set_defaults(fn=cmd_where)

    p = sub.add_parser("items", help="list benchmark items")
    p.add_argument("--suite", default="all",
                   choices=["all", "core", "reservation"])
    p.set_defaults(fn=cmd_items)

    p = sub.add_parser("selftest",
                       help="gate every gold against its own checkers")
    p.add_argument("ids", nargs="*", help="item ids (default: all)")
    p.add_argument("--suite", default="all",
                   choices=["all", "core", "reservation"])
    p.add_argument("--golds-only", action="store_true",
                   help="skip the tier report")
    p.set_defaults(fn=cmd_selftest)

    p = sub.add_parser("prompts", help="write the prompt files to the workspace")
    p.set_defaults(fn=cmd_prompts)

    p = sub.add_parser("score", help="score one answer file against one item")
    p.add_argument("--item", required=True, help="item id, e.g. P16 or R01")
    p.add_argument("--answer", help="path to a model answer")
    p.add_argument("--gold", action="store_true",
                   help="score the item's own gold instead")
    p.add_argument("--snapshot", default="")
    p.set_defaults(fn=cmd_score)

    # The adapter is positional, not a flag: `collect` forwards everything after
    # it to the adapter's own parser, and a flag it needed for itself would be
    # swallowed by that forwarding.
    p = sub.add_parser("collect", help="get answers from a model")
    p.add_argument("adapter", choices=["openai", "anthropic", "fork"],
                   help="openai reaches any /v1 endpoint via --base-url")
    p.set_defaults(fn=cmd_collect)

    p = sub.add_parser("score-runs", help="batch score the workspace runs/")
    p.set_defaults(fn=cmd_score_runs)

    p = sub.add_parser("report", help="comparison tables")
    p.set_defaults(fn=cmd_report)

    # A separate subcommand rather than a --compare-baseline flag on `report`:
    # "compare mine against the shipped arms" is a distinct operation, and it
    # needs its own flags, which a passthrough subcommand cannot also declare.
    p = sub.add_parser("compare",
                       help="your scored arm beside the shipped reference arms")
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("provenance",
                       help="check every answer still matches its prompt")
    p.set_defaults(fn=cmd_provenance)
    return ap


#: Subcommands that forward every remaining argument to a delegated tool.
_PASSTHROUGH = {"prompts", "score-runs", "collect", "report", "compare",
                "provenance"}

#: Global flags accepted before the subcommand name.
_GLOBAL_WITH_VALUE = {"--workspace"}


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """Cut argv at the subcommand, so a delegated tool's flags reach it intact.

    argparse cannot do this. Its REMAINDER does not reliably capture a leading
    "--flag", and parse_known_args separates an unknown "--csv" from its value
    and reorders them relative to the positionals. Both silently mangle the
    forwarded command line, so the split is explicit: everything after a
    passthrough subcommand is that tool's argv and this parser never sees it.
    """
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok in _GLOBAL_WITH_VALUE:
            i += 2
            continue
        if any(tok.startswith(g + "=") for g in _GLOBAL_WITH_VALUE):
            i += 1
            continue
        if tok.startswith("-"):          # --help, --version
            i += 1
            continue
        break                            # argv[i] is the subcommand
    if i >= len(argv):
        return argv, []
    if argv[i] == "collect":             # keeps its positional adapter name
        return argv[:i + 2], argv[i + 2:]
    if argv[i] in _PASSTHROUGH:
        return argv[:i + 1], argv[i + 1:]
    return argv, []


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    head, rest = _split_argv(argv)
    args = build_parser().parse_args(head)
    args.rest = rest
    if args.workspace:
        paths.set_workspace(args.workspace)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
