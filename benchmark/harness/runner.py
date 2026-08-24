"""
Benchmark v4 runner: load items, evaluate an answer (or the gold) against checkers,
optionally execute V1 availability items against a snapshot via the stub chi module.

Usage:
  python -m harness.runner --item items/P02.yaml --answer path/to/answer.md
  python -m harness.runner --item items/AV01.yaml --gold           # self-check
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from checks import run_checks  # noqa: E402

FENCE = re.compile(r"```[a-zA-Z0-9_]*\n(.*?)```", re.DOTALL)


def extract_code(answer_text: str) -> str:
    """Concatenate fenced code blocks; if none, treat whole text as code iff it parses."""
    blocks = FENCE.findall(answer_text)
    if blocks:
        return "\n\n".join(blocks)
    import ast
    try:
        ast.parse(answer_text)
        return answer_text
    except SyntaxError:
        return ""


def exec_v1(code: str, snapshot: Path, timeout=15):
    """Execute code in a subprocess with the stub chi package on sys.path and the
    snapshot injected. Returns (rc, stdout, stderr). CAUTION: executes model code;
    run only in a disposable environment."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(HERE / "stub_chi") + os.pathsep + env.get("PYTHONPATH", "")
    env["CHI_SNAPSHOT"] = str(snapshot)
    prelude = "def display(x):\n    print(x)\n\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(prelude + code)
        path = f.name
    try:
        p = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           timeout=timeout, env=env)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    finally:
        os.unlink(path)


def resolve_snapshot(item: dict, default: Path | None) -> Path | None:
    """A v5 item names the environment it is graded against; v4 items do not.

    Environment variation is the whole point of the reservation suite, so the
    item wins over the CLI default rather than the other way round.
    """
    name = item.get("snapshot")
    return (ROOT / "snapshots" / f"{name}.json") if name else default


def evaluate(item: dict, answer_text: str, snapshot: Path | None = None) -> dict:
    code = extract_code(answer_text)
    snapshot = resolve_snapshot(item, snapshot)
    # v5 decision checks grade against the snapshot; v4 checks ignore the extra.
    results = run_checks(code, answer_text, item.get("checkers", []),
                         extra={"snapshot": snapshot, "item": item})
    v1 = None
    if item.get("verification_level") == "V1" and snapshot is not None:
        if code.strip():
            rc, out, err = exec_v1(code, snapshot)
            exp = item.get("v1_expect", {})
            missing = [s for s in exp.get("stdout_contains_all", []) if s not in out]
            leaked = [s for s in exp.get("stdout_not_contains", []) if s in out]
            passed = rc == 0 and not missing and not leaked
            v1 = {"passed": passed, "rc": rc, "missing": missing, "leaked": leaked,
                  "stderr": err[-400:] if err else ""}
            results.append({"check": "v1_snapshot_exec", "group": "specifics",
                            "passed": passed,
                            "detail": f"rc={rc} missing={missing} leaked={leaked}",
                            "params": {}})
        else:
            results.append({"check": "v1_snapshot_exec", "group": "specifics",
                            "passed": False, "detail": "no executable code", "params": {}})
    by_group = {}
    for r in results:
        by_group.setdefault(r["group"], []).append(r["passed"])
    summary = {g: {"passed": sum(v), "total": len(v)} for g, v in by_group.items()}
    return {"item": item["id"], "all_passed": all(r["passed"] for r in results),
            "groups": summary, "results": results, "v1": v1}


def load_item(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", required=True)
    ap.add_argument("--answer", help="path to a model answer (markdown/text)")
    ap.add_argument("--gold", action="store_true", help="evaluate the item's own gold")
    ap.add_argument("--snapshot", default=str(ROOT / "snapshots" /
                                              "snapshot_synthetic_2026-07-04.json"))
    args = ap.parse_args()
    item = load_item(Path(args.item))
    if args.gold:
        text = "```python\n" + item["gold_spec"] + "\n```"
    else:
        text = Path(args.answer).read_text()
    rep = evaluate(item, text, Path(args.snapshot))
    print(json.dumps(rep, indent=2))
    sys.exit(0 if rep["all_passed"] else 1)


if __name__ == "__main__":
    main()
