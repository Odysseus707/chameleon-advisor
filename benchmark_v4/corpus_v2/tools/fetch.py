"""fetch: resolve catalog artifacts to repos and clone them. Stage 1.

Everything lands under corpus_v2/. Nothing is written to benchmark_v4/grounding/
or the workspace grounding/, because run_bench.py:90 globs grounding/*.md and
tier_assign.py:33 globs grounding/A*.md, and the frozen provenance hash depends
on both.

Policy, in the order it is applied per repo URL:

  trovi wrapper       ChameleonCloud/trovi_external_artifacts_deployment is a
                      generic import shim with no Chameleon code in it. The real
                      content lives in the Trovi artifact contents, which the
                      live API would expose. That API answers 404, so these are
                      recorded unfetchable rather than cloned as an empty shim.
  non-GitHub host     recorded unfetchable; there is no resolver for it.
  size over the cap   200 MB. Above it, sparse-checkout limited to *.ipynb,
                      *.py, README*, *.md, because several artifacts link huge
                      upstream research repos (tensorflow/models, dealii/dealii)
                      that must not be cloned whole.
  otherwise           shallow clone, depth 1, blobless.

Clones are keyed by owner/name, not by artifact, so a repo linked from several
artifacts is fetched once. mlflow-chi is linked from three. Each clone is
content-hashed so later stages can cache on hash and detect upstream drift.

  python corpus_v2/tools/fetch.py run [--jobs N] [--limit N] [--force]
  python corpus_v2/tools/fetch.py status
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import load_catalog, normalize_repo  # noqa: E402

CORPUS = HERE.parent
BENCH = CORPUS.parent
WORKSPACE = BENCH.parent

REPOS = CORPUS / "cache" / "repos"
STATE = CORPUS / "fetch_state.jsonl"

SIZE_CAP_MB = 200
SPARSE_PATTERNS = ["*.ipynb", "*.py", "README*", "*.md"]
TROVI_WRAPPER = "chameleoncloud/trovi_external_artifacts_deployment"

# Directories that are never part of artifact content.
SKIP_DIRS = {".git", ".github", "node_modules", "__pycache__", ".ipynb_checkpoints"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_git(args: list[str], cwd: Path | None = None, timeout: int = 900):
    """git with every interactive prompt disabled, so a private repo fails fast."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo")
    return subprocess.run(["git", *args], cwd=cwd, env=env, timeout=timeout,
                          capture_output=True, text=True)


def gh_repo_size_mb(repo_key: str) -> tuple[float | None, str | None]:
    """Repo size via the GitHub API, in MB. Returns (size, error)."""
    proc = subprocess.run(["gh", "api", f"repos/{repo_key}", "--jq", ".size"],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        err = proc.stderr.strip().splitlines()
        return None, (err[-1] if err else "gh api failed")
    try:
        return int(proc.stdout.strip()) / 1024.0, None   # the API reports KB
    except ValueError:
        return None, f"unparseable size {proc.stdout.strip()!r}"


def content_hash(root: Path) -> tuple[str, int, int]:
    """(sha256 over the tree, file count, total bytes), ignoring VCS metadata.

    Hashes relative path plus content for every file in sorted order, so the
    digest is stable across clones and machines and moves if any byte moves.
    """
    h = hashlib.sha256()
    n = total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if SKIP_DIRS & set(path.relative_to(root).parts):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        h.update(str(path.relative_to(root)).encode("utf-8"))
        h.update(hashlib.sha256(data).digest())
        n += 1
        total += len(data)
    return h.hexdigest(), n, total


def clone_shallow(url: str, dest: Path):
    return run_git(["clone", "--depth", "1", "--filter=blob:none",
                    "--quiet", url, str(dest)])


def clone_sparse(url: str, dest: Path):
    """Blobless no-checkout clone, then a non-cone sparse checkout.

    Non-cone mode is required: cone mode matches directories, and these are
    file globs that must apply at every depth.
    """
    p = run_git(["clone", "--depth", "1", "--filter=blob:none", "--no-checkout",
                 "--quiet", url, str(dest)])
    if p.returncode != 0:
        return p
    p = run_git(["sparse-checkout", "init", "--no-cone"], cwd=dest)
    if p.returncode != 0:
        return p
    p = run_git(["sparse-checkout", "set", *SPARSE_PATTERNS], cwd=dest)
    if p.returncode != 0:
        return p
    return run_git(["checkout"], cwd=dest)


def repo_dir(repo_key: str) -> Path:
    return REPOS / repo_key.replace("/", "__")


def fetch_one(url: str) -> dict:
    """Fetch a single repo URL. Idempotent per repo_key."""
    repo_key = normalize_repo(url)
    rec: dict = {"repo_url": url, "repo_key": repo_key, "fetch_status": "error",
                 "mode": None, "repo_size_mb": None, "content_hash": None,
                 "n_files": None, "total_bytes": None, "error": None,
                 "fetched_utc": now()}

    if repo_key == TROVI_WRAPPER:
        rec.update(fetch_status="unfetchable", mode="trovi_wrapper", error=(
            "generic import wrapper, no Chameleon code on GitHub; real content "
            "is in the Trovi artifact contents and the Trovi API is "
            "unreachable (404)"))
        return rec

    if not re.search(r"github\.com", url, re.I):
        rec.update(fetch_status="unfetchable", mode="non_github",
                   error="not a GitHub URL; no resolver for this host")
        return rec

    dest = repo_dir(repo_key)
    size_mb, size_err = gh_repo_size_mb(repo_key)
    rec["repo_size_mb"] = round(size_mb, 2) if size_mb is not None else None
    if size_err and size_mb is None:
        # Size unknown. Try a shallow clone anyway: the repo may be fine and
        # only the API call failed. A genuinely missing repo fails at clone.
        rec["error"] = f"size lookup failed: {size_err}"

    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    over_cap = size_mb is not None and size_mb > SIZE_CAP_MB
    mode = "sparse" if over_cap else "shallow"
    proc = clone_sparse(url, dest) if over_cap else clone_shallow(url, dest)

    if proc.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True)
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        rec.update(fetch_status="unfetchable", mode=mode,
                   error=(tail[-1] if tail else "clone failed"))
        return rec

    digest, n_files, total = content_hash(dest)
    rec.update(fetch_status="sparse" if over_cap else "cloned", mode=mode,
               content_hash=digest, n_files=n_files, total_bytes=total)
    return rec


def load_state() -> dict[str, dict]:
    if not STATE.exists():
        return {}
    out = {}
    for line in STATE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["repo_url"]] = r
    return out


def save_state(state: dict[str, dict]) -> None:
    STATE.write_text(
        "".join(json.dumps(state[k], ensure_ascii=False) + "\n"
                for k in sorted(state)), encoding="utf-8")


def load_fetch_state() -> dict[str, dict]:
    """Public accessor for later stages, keyed by repo_url."""
    return load_state()


def per_artifact_reachable(catalog, state) -> dict[str, bool]:
    ok = {"cloned", "sparse"}
    out = {}
    for a in catalog:
        if a["status"] == "excluded":
            continue
        out[a["artifact_id"]] = any(
            state.get(u, {}).get("fetch_status") in ok for u in a["repo_urls"])
    return out


def run(jobs: int, limit: int | None, force: bool) -> int:
    catalog = load_catalog()
    REPOS.mkdir(parents=True, exist_ok=True)
    state = {} if force else load_state()

    todo: list[str] = []
    for a in catalog:
        if a["status"] == "excluded":
            continue
        for u in a["repo_urls"]:
            if u not in state and u not in todo:
                todo.append(u)
    if limit:
        todo = todo[:limit]

    print(f"[fetch] {len(state)} already in state, {len(todo)} to fetch, "
          f"{jobs} workers, cap {SIZE_CAP_MB} MB")
    done = 0
    with futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(fetch_one, u): u for u in todo}
        for fut in futures.as_completed(futs):
            url = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:                       # noqa: BLE001
                rec = {"repo_url": url, "repo_key": normalize_repo(url),
                       "fetch_status": "error", "mode": None,
                       "repo_size_mb": None, "content_hash": None,
                       "n_files": None, "total_bytes": None,
                       "error": f"{type(e).__name__}: {e}", "fetched_utc": now()}
            state[url] = rec
            done += 1
            size = f"{rec['repo_size_mb']}MB" if rec["repo_size_mb"] else "?"
            print(f"  [{done}/{len(todo)}] {rec['fetch_status']:11} "
                  f"{rec['repo_key']} ({size})"
                  + (f"  {rec['error']}" if rec["error"] else ""), flush=True)
            if done % 10 == 0:
                save_state(state)
    save_state(state)
    return status()


def status() -> int:
    state = load_state()
    catalog = load_catalog()
    by_status: dict[str, int] = {}
    for r in state.values():
        by_status[r["fetch_status"]] = by_status.get(r["fetch_status"], 0) + 1

    print(f"\n[fetch status] {len(state)} repo URLs recorded")
    for k in sorted(by_status):
        print(f"  {k:12} {by_status[k]}")

    ok = {"cloned", "sparse"}
    reachable = per_artifact_reachable(catalog, state)
    have = sum(1 for v in reachable.values() if v)
    included = [a for a in catalog if a["status"] == "included"]
    print(f"\n[artifacts] {len(included)} included, {have} with at least one "
          f"fetched repo, {len(included) - have} with none")
    n_ok = sum(1 for r in state.values() if r["fetch_status"] in ok)
    uniq = {r["content_hash"] for r in state.values()
            if r["fetch_status"] in ok and r["content_hash"]}
    print(f"[dedupe] {n_ok} successful clones over {len(uniq)} unique "
          f"content hashes")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--jobs", type=int, default=8)
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--force", action="store_true",
                   help="ignore existing state and refetch everything")
    sub.add_parser("status")
    args = ap.parse_args()
    return run(args.jobs, args.limit, args.force) if args.cmd == "run" else status()


if __name__ == "__main__":
    raise SystemExit(main())
