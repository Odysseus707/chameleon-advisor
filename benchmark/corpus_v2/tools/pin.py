"""pin: record exactly which commit of each artifact the wing is built on. Stage 5.

WHAT A PIN IS
A git repository is a chain of snapshots ("commits"), each named by a 40-hex
fingerprint ("sha"). Naming the sha is what makes "we used artifact A7"
reproducible: without it, A7 means whatever that repo happens to contain today.

WHICH SNAPSHOT WE PIN, AND WHY IT IS NOT TROVI'S
Two candidate answers exist for "which snapshot is artifact A7":

  1. the commit the clone sits at - whatever was newest when fetch.py ran
  2. the commit Trovi's contents URN names - what the author published

They disagree for 73 of the 79 artifacts carrying a Trovi git URN, and for 52
of those the difference includes .py/.ipynb files, i.e. the provisioning code
itself. That matters because EVERYTHING already measured - node_types_observed,
site_observed, the advisor score, the reviewed A/B/C tier, and therefore which
91 artifacts are in this wing at all - was computed by triage.py and rank.py
scanning the CLONE. Pinning to Trovi's commit would leave those facts
describing a tree nobody reads.

So the pin is the clone's commit, and Trovi's is recorded beside it:

    pinned_sha          the commit we use, read, and measured
    trovi_declared_sha  what Trovi names (may be null: 12 have no git URN)
    pin_matches_trovi   whether they agree
    diverges_in_code    whether the difference touches .py/.ipynb
    divergent_files     which files, capped

Nothing is hidden and nothing has to be redone. The cost is stated plainly: the
wing is built on these repos as fetched, not as published, and every record says
so. A later reconciliation pass can re-fetch and re-measure deliberately.

  python corpus_v2/tools/pin.py run
  python corpus_v2/tools/pin.py run --dry-run   # report, write nothing
  python corpus_v2/tools/pin.py run --offline   # never touch the network
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import normalize_repo                              # noqa: E402
from fetch import repo_dir                                      # noqa: E402
from select_wing import (ARTIFACTS_DIR, WORKSPACE,              # noqa: E402
                         load_registry, render_artifact)

#: Where provisioning lives. A diff confined to READMEs does not change what an
#: extraction would find; a diff in these files does.
CODE_SUFFIXES = (".py", ".ipynb")

#: Divergent files are recorded for triage, not archaeology. The full list for a
#: large repo is thousands of entries and would bury the record.
MAX_DIVERGENT_FILES = 12

GIT_TIMEOUT = 120


def git(repo: Path, *args, timeout=GIT_TIMEOUT):
    """(returncode, stdout). stderr is folded in only on failure."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, ""
    return p.returncode, p.stdout.strip()


def head_sha(repo: Path) -> str | None:
    rc, out = git(repo, "rev-parse", "HEAD")
    return out if rc == 0 and len(out) == 40 else None


def has_commit(repo: Path, sha: str) -> bool:
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}")[0] == 0


def try_fetch_commit(repo: Path, sha: str) -> bool:
    """Ask the remote for one specific commit. Used only to complete the
    divergence record - we never check it out."""
    rc, _ = git(repo, "fetch", "--depth", "1", "origin", sha, timeout=180)
    return rc == 0 and has_commit(repo, sha)


def divergence(repo: Path, pinned: str, trovi: str):
    """(diverges_in_code, files) between the pinned commit and Trovi's."""
    rc, out = git(repo, "diff", "--name-only", trovi, pinned)
    if rc != 0:
        return None, []
    files = [f for f in out.splitlines() if f.strip()]
    in_code = any(f.endswith(CODE_SUFFIXES) for f in files)
    return in_code, sorted(files)[:MAX_DIVERGENT_FILES]


def pin_one(rec: dict, offline: bool) -> dict:
    """Resolve one artifact. Mutates and returns the record."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    repo = repo_dir(normalize_repo(rec["repo_url"]))
    trovi = rec.get("trovi_declared_sha")

    if not repo.is_dir():
        rec.update(pinned_sha=None, pin_source=None, pin_status="no_clone",
                   pinned_utc=now, pin_matches_trovi=None,
                   trovi_sha_present=None, diverges_in_code=None,
                   divergent_files=[])
        return rec

    sha = head_sha(repo)
    if sha is None:
        rec.update(pinned_sha=None, pin_source=None, pin_status="not_a_git_repo",
                   pinned_utc=now, pin_matches_trovi=None,
                   trovi_sha_present=None, diverges_in_code=None,
                   divergent_files=[])
        return rec

    rec.update(pinned_sha=sha, pin_source="clone_head",
               pin_status="verified", pinned_utc=now)

    if not trovi:
        # 12 artifacts: Trovi's contents URN is not a git URN at all
        # (chameleon / heat_template / chi-tacc / chi-uc / kvm-tacc), so there
        # is no published commit to compare against. Not a failure.
        rec.update(pin_matches_trovi=None, trovi_sha_present=None,
                   diverges_in_code=None, divergent_files=[])
        return rec

    present = has_commit(repo, trovi)
    if not present and not offline:
        present = try_fetch_commit(repo, trovi)
    rec["trovi_sha_present"] = present
    rec["pin_matches_trovi"] = (sha == trovi)

    if sha == trovi:
        rec.update(diverges_in_code=False, divergent_files=[])
    elif present:
        in_code, files = divergence(repo, sha, trovi)
        rec.update(diverges_in_code=in_code, divergent_files=files)
    else:
        # Trovi names a commit we cannot obtain, so the divergence is real but
        # unmeasurable. Recorded as unknown rather than guessed at.
        rec.update(diverges_in_code=None, divergent_files=[])
        rec["pin_status"] = "verified_trovi_unreachable"
    return rec


def run(dry_run: bool, offline: bool) -> int:
    reg = load_registry()
    records = reg["artifacts"]
    print(f"[pin] {len(records)} artifacts"
          f"{'  (offline)' if offline else ''}\n")

    for rec in records:
        pin_one(rec, offline)

    def tally(key):
        d: dict = {}
        for r in records:
            d[str(r.get(key))] = d.get(str(r.get(key)), 0) + 1
        return dict(sorted(d.items()))

    print(f"  pin_status         {tally('pin_status')}")
    print(f"  pin_matches_trovi  {tally('pin_matches_trovi')}")
    print(f"  trovi_sha_present  {tally('trovi_sha_present')}")
    print(f"  diverges_in_code   {tally('diverges_in_code')}")

    unpinned = [r["id"] for r in records if not r["pinned_sha"]]
    if unpinned:
        print(f"\n  UNPINNED ({len(unpinned)}): {', '.join(unpinned)}")
        print("  These have no usable clone. Fix the fetch before proceeding;")
        print("  a record with no pin cannot be grounded or extracted.")

    unreachable = [r["id"] for r in records
                   if r["pin_status"] == "verified_trovi_unreachable"]
    if unreachable:
        print(f"\n  Trovi commit unobtainable ({len(unreachable)}): "
              f"{', '.join(unreachable)}")
        print("  Pinned to the clone as usual; the divergence is simply not")
        print("  measurable for these, and is recorded as unknown, not false.")

    if dry_run:
        print("\n[dry-run] nothing written")
        return 0

    wrote = 0
    for rec in records:
        path = ARTIFACTS_DIR / f"{rec['id']}.yaml"
        # `pinned_utc` is stamped with now() on every run, so a naive compare
        # always differs and every record is rewritten - churning 90 files and
        # failing the parity gate on a re-run that changed nothing. Same shape
        # as select_wing's generated_utc. Only bump the timestamp when the pin
        # itself actually moved.
        if path.exists():
            import yaml
            old_rec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            substantive = [k for k in rec
                           if k != "pinned_utc" and old_rec.get(k) != rec[k]]
            if not substantive:
                rec["pinned_utc"] = old_rec.get("pinned_utc", rec["pinned_utc"])
        text = render_artifact(rec)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        path.write_text(text, encoding="utf-8")
        wrote += 1
    print(f"\n[written] {wrote} record(s) updated in "
          f"{ARTIFACTS_DIR.relative_to(WORKSPACE)}")
    return 1 if unpinned else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run",))
    ap.add_argument("--dry-run", action="store_true",
                    help="report the pins without writing them")
    ap.add_argument("--offline", action="store_true",
                    help="never contact a remote; unobtainable Trovi commits "
                         "are recorded as absent rather than fetched")
    args = ap.parse_args()
    return run(args.dry_run, args.offline)


if __name__ == "__main__":
    raise SystemExit(main())
