"""run_bench: scripted benchmark runs writing into the scorer's existing layout.

Adapters:
  fork             the RAG-docs-chameleon pipeline in-process (retrieval +
                   advisor gate/inject + LLM), --advisor on|off
  anthropic/openai one prompts/<condition>/<ITEM>.txt per request, model and
                   params pinned in bench_config.yaml, retries with backoff
                   (code-only for now: no keys configured; use --dry-run)
  production-stub  reserved for a future production deployment; refuses to run

Invariants (see docs/architecture/harness-plan.md):
  * responses are written VERBATIM to runs/<condition>/<system>/<ITEM>.md —
    fences intact, prose intact; existing non-empty files are never touched
  * telemetry sidecars (<ITEM>.telemetry.json) and manifest.json are invisible
    to the scorer's glob ('runs/*/*/*.md'); scorer code is never modified
  * every batch emits manifest.json: model+params, timestamps, host, item
    statuses, fork git state, content-hashes of item bank / grounding /
    snapshot (the parent repo has no commits, so content hashes stand in
    for git SHAs)

Pilot (on the node):
  cd ~/benchmark && ~/RAG-docs-chameleon/.venv/bin/python tools/run_bench.py \
      --adapter fork --pilot
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from chi_edge_bench.paths import (default_snapshot, grounding_dir, items_dir,
                                  prompts_dir, runs_dir, workspace)

HERE = Path(__file__).resolve().parent
CONDITIONS = ("blind", "matched", "heldout", "uncovered")
# NOTE: a function, not a constant - see chi_edge_bench.paths.workspace().
FORK_SYSTEMS = {True: "s4-fork-on", False: "s5-fork-off"}
PILOT_DEFAULT = ["P01", "P16", "N01", "N06", "AV01"]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_paths(paths) -> str | None:
    paths = sorted(p for p in paths if p.is_file())
    if not paths:
        return None
    h = hashlib.sha256()
    for p in paths:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def git_info(repo: Path) -> dict:
    def g(*a):
        try:
            r = subprocess.run(["git", "-C", str(repo), *a],
                               capture_output=True, text=True, timeout=20)
            return r.stdout.strip()
        except Exception:
            return ""
    head = g("rev-parse", "HEAD") or None
    status = g("status", "--porcelain")
    diff = g("diff", "HEAD")
    dirty = bool(status)
    work = hashlib.sha256((status + "\n" + diff).encode()).hexdigest() if dirty else None
    return {"head": head, "dirty": dirty, "worktree_sha256": work}


def provenance_hashes(cfg: dict) -> dict:
    adv_dir = (cfg.get("fork") or {}).get("advisor_grounding")
    adv = None
    if adv_dir:
        p = Path(os.path.expanduser(adv_dir))
        if p.is_dir():
            adv = sha256_paths(p.rglob("*.md"))
    return {
        "item_bank_sha256": sha256_paths(items_dir().glob("*.yaml")),
        "bench_grounding_sha256": sha256_paths(grounding_dir().glob("*.md")),
        "advisor_grounding_sha256": adv,
        "snapshot_sha256": sha256_paths([default_snapshot()]),
    }


def read_prompt(condition: str, item_id: str) -> str:
    return (prompts_dir() / condition / f"{item_id}.txt").read_text(encoding="utf-8")


def items_for_condition(condition: str) -> list[str]:
    return sorted(p.stem for p in (prompts_dir() / condition).glob("*.txt"))


def with_retries(fn, tries: int = 5, base: float = 2.0):
    for i in range(tries):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001 — API errors vary by SDK
            if i == tries - 1:
                raise
            wait = base * (2 ** i)
            print(f"    retry {i + 1}/{tries - 1} after error: {e} (sleep {wait:.0f}s)")
            time.sleep(wait)


# --------------------------------------------------------------------------
# adapters
# --------------------------------------------------------------------------
class ForkAdapter:
    """RAG-docs-chameleon pipeline in-process (see harness-plan.md §3)."""

    name = "fork"

    def __init__(self):
        self.advisor_on = False

    def prepare(self, cfg: dict, dry_run: bool = False):
        fc = cfg.get("fork") or {}
        for k, v in (fc.get("env") or {}).items():
            os.environ.setdefault(k, str(v))
        self.gate = float(fc.get("gate", os.environ.get("ADVISOR_GATE", "1.0")))
        self.model = os.environ.get("LLM_MODEL", "")
        self.params = {"endpoint": os.environ.get("LLM_API_BASE", ""), "gate": self.gate}
        if dry_run:
            return
        root = Path(os.path.expanduser(fc["root"]))
        sys.path.insert(0, str(root))
        adv_root = fc.get("advisor_root")
        if adv_root:
            sys.path.insert(0, str(Path(os.path.expanduser(adv_root))))
        os.chdir(root)  # rag.py resolves vect_store/ relative to the fork root
        import advisor_room  # noqa: PLC0415
        import rag  # noqa: PLC0415
        self._rag, self._ar = rag, advisor_room
        self.vs = rag.load_vectorstore()
        self.parents = rag.load_parents()
        self.chain = rag.create_llm_chain()

    def warm_advisor(self):
        self._ar.get_room()  # asserts bge embedder, loads artifact_store.json

    def answer(self, item_id: str, prompt_text: str):
        q = prompt_text.strip()
        tel = {
            "advisor_enabled": self.advisor_on, "gate": self.gate,
            "gate_score": None, "fired": False, "advisory": None,
            "grounded_by": None, "produced_by": None, "model": self.model,
        }
        t0 = time.time()
        srcs, ctx, _ = self._rag.build_context(q, self.vs, self.parents)
        tel["retrieval_s"] = round(time.time() - t0, 2)
        tel["retrieval_sources"] = [list(s) if isinstance(s, (tuple, list)) else s
                                    for s in list(srcs)]
        if self.advisor_on:
            t1 = time.time()
            tel["gate_score"] = self._ar.classify_top(q)
            tel["fired"] = self._ar.should_fire(q, self.gate)
            if tel["fired"]:
                advisory = self._ar.advise(q)
                tel["advisory"] = advisory
                m = re.search(r"grounded_by=\[([^\]]*)\]", advisory)
                tel["grounded_by"] = re.findall(r"'([^']+)'", m.group(1)) if m else []
                m = re.search(r"produced_by=(\w+)", advisory)
                tel["produced_by"] = m.group(1) if m else None
                # exact production inject (web_rag.py:472-474)
                ctx += "\n\n=== EDGE RESOURCE ADVISORY ===\n\n" + advisory
            tel["advisor_s"] = round(time.time() - t1, 2)
        t2 = time.time()
        resp = self.chain.invoke(
            {"question": q, "context": ctx, "history": []}
        ).content or ""
        tel["llm_s"] = round(time.time() - t2, 2)
        return resp, tel


class AnthropicAdapter:
    name = "anthropic"

    def prepare(self, cfg: dict, dry_run: bool = False):
        c = cfg.get("anthropic") or {}
        self.model = c.get("model", "")
        self.params = dict(c.get("params") or {})
        self.system_dir = c.get("system", "s3-sonnet")
        if dry_run:
            return
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY not set — API runs are disabled by "
                             "policy (zero spend); use --dry-run.")
        import anthropic  # noqa: PLC0415
        self.client = anthropic.Anthropic()

    def answer(self, item_id: str, prompt_text: str):
        def call():
            resp = self.client.messages.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt_text}],
                **self.params,
            )
            return "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text")
        t0 = time.time()
        text = with_retries(call)
        return text, {"model": self.model, "params": self.params,
                      "llm_s": round(time.time() - t0, 2)}


class OpenAIAdapter:
    name = "openai"

    def prepare(self, cfg: dict, dry_run: bool = False):
        c = cfg.get("openai") or {}
        self.model = c.get("model", "")
        self.params = dict(c.get("params") or {})
        self.system_dir = c.get("system", "s2-gpt")
        if dry_run:
            return
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY not set — API runs are disabled by "
                             "policy (zero spend); use --dry-run.")
        from openai import OpenAI  # noqa: PLC0415
        self.client = OpenAI()

    def answer(self, item_id: str, prompt_text: str):
        def call():
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt_text}],
                **self.params,
            )
            return resp.choices[0].message.content or ""
        t0 = time.time()
        text = with_retries(call)
        return text, {"model": self.model, "params": self.params,
                      "llm_s": round(time.time() - t0, 2)}


class ProductionStubAdapter:
    name = "production-stub"

    def prepare(self, cfg: dict, dry_run: bool = False):
        raise SystemExit(
            "production-stub is a reserved adapter slot: it will target the "
            "production Chameleon chatbot deployment once one exists (endpoint + "
            "auth to be added in bench_config.yaml). It writes nothing today.")

    def answer(self, item_id: str, prompt_text: str):  # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------
# batch runner
# --------------------------------------------------------------------------
def run_batch(adapter, items: list[str], condition: str, system: str,
              cfg: dict, dry_run: bool) -> dict:
    out_dir = runs_dir() / condition / system
    statuses: dict[str, str] = {}
    started = now_iso()
    print(f"== batch: adapter={adapter.name} condition={condition} "
          f"system={system} items={len(items)}{' [DRY-RUN]' if dry_run else ''}")
    for item_id in items:
        target = out_dir / f"{item_id}.md"
        if target.exists() and target.stat().st_size > 0:
            statuses[item_id] = "skipped_existing_nonempty"
            print(f"  {item_id}: SKIP (existing non-empty response — never modified)")
            continue
        try:
            prompt = read_prompt(condition, item_id)
        except FileNotFoundError:
            statuses[item_id] = "error:no_prompt"
            print(f"  {item_id}: ERROR no prompts/{condition}/{item_id}.txt")
            continue
        if dry_run:
            statuses[item_id] = "dry_run"
            print(f"  {item_id}: would call model={getattr(adapter, 'model', '?')} "
                  f"params={getattr(adapter, 'params', {})} -> {target}")
            continue
        try:
            t0 = time.time()
            resp, tel = adapter.answer(item_id, prompt)
            out_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(resp, encoding="utf-8")  # VERBATIM — no rewrap/strip
            tel.update({"item": item_id, "condition": condition, "system": system,
                        "adapter": adapter.name, "created": now_iso(),
                        "total_s": round(time.time() - t0, 2),
                        "response_chars": len(resp),
                        "n_code_fences": resp.count("```") // 2})
            (out_dir / f"{item_id}.telemetry.json").write_text(
                json.dumps(tel, indent=2, default=str), encoding="utf-8")
            statuses[item_id] = "written"
            print(f"  {item_id}: written ({len(resp)} chars, "
                  f"{tel.get('total_s')}s, fired={tel.get('fired')})")
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            statuses[item_id] = f"error:{e}"
            print(f"  {item_id}: ERROR {e}")
    manifest = {
        "created": started, "finished": now_iso(), "host": socket.gethostname(),
        "adapter": adapter.name, "system": system, "condition": condition,
        "model": getattr(adapter, "model", None),
        "params": getattr(adapter, "params", None),
        "advisor_enabled": getattr(adapter, "advisor_on", None),
        "fork_git": (git_info(Path(os.path.expanduser(cfg["fork"]["root"])))
                     if adapter.name == "fork" and (cfg.get("fork") or {}).get("root")
                     else None),
        "hashes": provenance_hashes(cfg),
        "items": statuses, "argv": sys.argv,
    }
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------
# pilot: fork adapter, advisor on + off, then a scorer-compat summary
# --------------------------------------------------------------------------
def hash_other_runs(exclude: set[str]) -> str:
    files = [p for p in runs_dir().rglob("*.md")
             if not (len(p.relative_to(runs_dir()).parts) >= 2
                     and p.relative_to(runs_dir()).parts[1] in exclude)]
    return sha256_paths(files) or "empty"


def pilot_summary(items: list[str], baseline_ok: bool):
    from chi_edge_bench.harness.runner import (evaluate,  # noqa: PLC0415
                                               extract_code, load_item)

    # Paths are reported workspace-relative, which is what the notebook
    # contract below is stated in ("runs/<cond>/<system>/<ITEM>.md"). This used
    # to rely on an os.chdir into the benchmark root; it now globs an absolute
    # directory and relativises afterwards.
    matched = sorted(p.relative_to(workspace()).as_posix()
                     for p in runs_dir().rglob("*.md"))
    ours, bad_depth, bad_stems = [], [], []
    for path in matched:
        parts = path.split("/")
        if len(parts) != 4:
            bad_depth.append(path)
            continue
        _, cond, system, fname = parts
        stem = fname[:-3]
        if not (items_dir() / f"{stem}.yaml").exists():
            bad_stems.append(path)
            continue
        if system in ("s4-fork-on", "s5-fork-off") and stem in items:
            ours.append((cond, system, stem, path))

    print("\n" + "=" * 74)
    print("PILOT SUMMARY — scorer-compat check (notebook contract: "
          "glob 'runs/*/*/*.md')")
    print("=" * 74)
    print(f"layout: runs/<condition>/<system>/<ITEM>.md | glob matched "
          f"{len(matched)} files, {len(ours)} from this pilot")
    hdr = f"{'item':6}{'system':13}{'fences':8}{'verdict':9}{'groups':22}" \
          f"{'gate':7}{'fired':7}{'by':10}"
    print(hdr)
    print("-" * len(hdr))
    for cond, system, stem, path in sorted(ours, key=lambda r: (r[2], r[1])):
        text = Path(path).read_text(encoding="utf-8")
        fences = "yes" if "```" in text else "no"
        rep = evaluate(load_item(items_dir() / f"{stem}.yaml"), text,
                       default_snapshot())
        groups = " ".join(f"{g[:4]}={v['passed']}/{v['total']}"
                          for g, v in sorted(rep["groups"].items()))
        tel_file = Path(str(Path(path))[:-3] + ".telemetry.json")
        gate = fired = by = "-"
        if tel_file.exists():
            tel = json.loads(tel_file.read_text())
            gate = ("%.2f" % tel["gate_score"]) if tel.get("gate_score") is not None else "-"
            fired = "yes" if tel.get("fired") else "no"
            by = tel.get("produced_by") or "-"
        verdict = "PASS" if rep["all_passed"] else "FAIL"
        code_ok = "yes" if extract_code(text).strip() else "no"
        print(f"{stem:6}{system:13}{fences + '/' + code_ok:8}{verdict:9}"
              f"{groups:22}{gate:7}{fired:7}{by:10}")
    ok = lambda b: "OK " if b else "FAIL"  # noqa: E731
    print("-" * len(hdr))
    print(f"assertions: [{ok(not bad_depth)}] 3-level paths only   "
          f"[{ok(not bad_stems)}] stems resolve to items/   "
          f"[{ok(True)}] sidecars invisible to glob   "
          f"[{ok(baseline_ok)}] pre-existing runs/ files unmodified")
    print("(fences column = raw ``` present / extract_code() non-empty; "
          "verdicts computed by harness.runner.evaluate — scorer code untouched)")


def cmd_pilot(cfg: dict, args) -> None:
    items = (cfg.get("pilot") or {}).get("items") or PILOT_DEFAULT
    baseline = hash_other_runs(exclude=set(FORK_SYSTEMS.values()))
    adapter = ForkAdapter()
    adapter.prepare(cfg, dry_run=args.dry_run)
    if args.dry_run:
        for on in (True, False):
            adapter.advisor_on = on
            run_batch(adapter, items, "blind", FORK_SYSTEMS[on], cfg, True)
        return
    adapter.advisor_on = True
    adapter.warm_advisor()
    run_batch(adapter, items, "blind", FORK_SYSTEMS[True], cfg, False)
    adapter.advisor_on = False
    run_batch(adapter, items, "blind", FORK_SYSTEMS[False], cfg, False)
    baseline_ok = hash_other_runs(exclude=set(FORK_SYSTEMS.values())) == baseline
    pilot_summary(items, baseline_ok)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--adapter", default="fork",
                    choices=["fork", "anthropic", "openai", "production-stub"])
    ap.add_argument("--advisor", default="on", choices=["on", "off"],
                    help="fork adapter: advisor room enabled? (-> s4/s5 system dir)")
    ap.add_argument("--conditions", default="blind",
                    help="comma-separated (API adapters); fork is always blind")
    ap.add_argument("--items", default="",
                    help="comma-separated item ids (default: all with prompts)")
    ap.add_argument("--system", default="", help="override target system dir")
    ap.add_argument("--config", default=str(HERE / "bench_config.yaml"))
    ap.add_argument("--dry-run", action="store_true",
                    help="print targets/models/params; no network, no writes")
    ap.add_argument("--pilot", action="store_true",
                    help="fork adapter: 5 pilot items, advisor on AND off, "
                         "then a scorer-compat summary")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text()) or {}

    if args.pilot:
        cmd_pilot(cfg, args)
        return

    adapters = {"fork": ForkAdapter, "anthropic": AnthropicAdapter,
                "openai": OpenAIAdapter, "production-stub": ProductionStubAdapter}
    adapter = adapters[args.adapter]()
    adapter.prepare(cfg, dry_run=args.dry_run)

    if args.adapter == "fork":
        adapter.advisor_on = args.advisor == "on"
        if adapter.advisor_on and not args.dry_run:
            adapter.warm_advisor()
        conditions = ["blind"]
        system = args.system or FORK_SYSTEMS[adapter.advisor_on]
    else:
        conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
        for c in conditions:
            if c not in CONDITIONS:
                raise SystemExit(f"unknown condition {c!r} (choose from {CONDITIONS})")
        system = args.system or adapter.system_dir

    for condition in conditions:
        items = ([i.strip() for i in args.items.split(",") if i.strip()]
                 or items_for_condition(condition))
        run_batch(adapter, items, condition, system, cfg, args.dry_run)


if __name__ == "__main__":
    main()
