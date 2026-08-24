"""catalog: parse the Trovi compendium into a stable, resumable catalog.

Stage 1a. Consumes benchmark/compendium/compendium.txt, the offline capture
of the Trovi catalog. The live API at trovi.chameleoncloud.org/api/artifacts
answers 404, so the compendium is the only catalog surface available.

Compendium grammar, one artifact per block:

    ## <trovi title>
       tags: <comma-separated>        (optional; 164 of 205 blocks have it)
       <url>                          (one or more)

Produces catalog.jsonl with a stable artifact_id, plus the two policy
decisions that must happen before any network call:

  exclusions        cloud-gpu-inference is excluded outright.
                    edge-cpu-inference is v1 (A6), already ingested and under
                    mentor review: excluded from re-ingest, and flagged.
  near-duplicates   any artifact whose repo_url or title collides with a v1
                    artifact is flagged. The A4 / MCP_SLM_Project drift is the
                    reason this exists: nothing in the workspace detects it.

v1 identity is read from benchmark/extractions/A*.yaml rather than
hardcoded, so the duplicate check tracks the registry instead of drifting from
it. Those files are read, never written.

  python corpus_v2/tools/catalog.py build
  python corpus_v2/tools/catalog.py show <artifact_id>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent
BENCH = CORPUS.parent
WORKSPACE = BENCH.parent

COMPENDIUM = BENCH / "compendium" / "compendium.txt"
TROVI_RECORDS = BENCH / "compendium" / "trovi_records.json"
EXTRACTIONS = BENCH / "extractions"
CATALOG = CORPUS / "catalog.jsonl"

# Excluded outright by the brief.
HARD_EXCLUDE_SLUGS = {"cloud-gpu-inference"}
# Already ingested in v1 and under mentor review: do not re-ingest, do not edit,
# but do flag if the catalog surfaces it again.
V1_INGESTED_SLUGS = {"edge-cpu-inference"}

TITLE_SIMILARITY_FLAG = 0.85


def slugify(text: str, maxlen: int = 64) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("-")
    return s or "artifact"


def repo_slug(url: str) -> str:
    """Last path segment of a repo URL, lowercased, for exclusion matching."""
    return url.rstrip("/").split("/")[-1].lower().removesuffix(".git")


def normalize_repo(url: str) -> str:
    """owner/name lowercased, so URL spelling variants compare equal."""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/#?]+)", url, re.I)
    if not m:
        return url.rstrip("/").lower()
    return f"{m.group(1).lower()}/{m.group(2).lower().removesuffix('.git')}"


def parse_compendium(path: Path) -> list[dict]:
    """Parse the compendium into ordered blocks. Tolerates missing tags."""
    artifacts: list[dict] = []
    current: dict | None = None
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if raw.startswith("## "):
            current = {"trovi_title": raw[3:].strip(), "tags": [],
                       "repo_urls": [], "source_line": lineno}
            artifacts.append(current)
        elif current is None:
            continue
        elif line.lower().startswith("tags:"):
            current["tags"] = [t.strip() for t in line[5:].split(",") if t.strip()]
        elif line.startswith(("http://", "https://")):
            if line not in current["repo_urls"]:
                current["repo_urls"].append(line)
    return artifacts


def assign_ids(artifacts: list[dict]) -> None:
    """Stable slug ids. Collisions get a numeric suffix in catalog order.

    Three MLFlow variants share a repo and differ only by title, so ids come
    from the title, not the repo.
    """
    seen: dict[str, int] = {}
    for a in artifacts:
        base = slugify(a["trovi_title"])
        n = seen.get(base, 0) + 1
        seen[base] = n
        a["artifact_id"] = base if n == 1 else f"{base}-{n}"


def load_v1_registry() -> list[dict]:
    """v1 artifact identity, read live from extractions/A*.yaml (read-only)."""
    out = []
    for p in sorted(EXTRACTIONS.glob("A*.yaml")):
        text = p.read_text(encoding="utf-8")
        aid = re.search(r"^artifact_id:\s*(\S+)", text, re.M)
        url = re.search(r"^repo_url:\s*(\S+)", text, re.M)
        title = re.search(r"^title:\s*(.+)$", text, re.M)
        out.append({
            "v1_id": aid.group(1) if aid else p.stem,
            "repo_url": url.group(1) if url else "",
            "title": title.group(1).strip() if title else "",
        })
    return out


def apply_policy(artifacts: list[dict], v1: list[dict]) -> None:
    """Set status / exclusion_reason / dup_of / dup_basis on every artifact."""
    v1_by_repo = {normalize_repo(r["repo_url"]): r for r in v1 if r["repo_url"]}

    for a in artifacts:
        a["status"] = "included"
        a["exclusion_reason"] = None
        a["dup_of"] = None
        a["dup_basis"] = None

        slugs = {repo_slug(u) for u in a["repo_urls"]}

        hit = slugs & HARD_EXCLUDE_SLUGS
        if hit:
            a["status"] = "excluded"
            a["exclusion_reason"] = (
                f"brief exclusion: {sorted(hit)[0]} is excluded outright")

        hit = slugs & V1_INGESTED_SLUGS
        if hit and a["status"] == "included":
            a["status"] = "excluded"
            a["exclusion_reason"] = (
                f"already ingested in v1 and under mentor review: {sorted(hit)[0]}. "
                "Do not re-ingest, do not edit its existing files.")

        # Near-duplicate of a v1 artifact: repo URL first, then title.
        for u in a["repo_urls"]:
            match = v1_by_repo.get(normalize_repo(u))
            if match:
                a["dup_of"] = match["v1_id"]
                a["dup_basis"] = f"repo_url == {match['repo_url']}"
                break
        if not a["dup_of"]:
            for r in v1:
                if not r["title"]:
                    continue
                score = SequenceMatcher(
                    None, a["trovi_title"].lower(), r["title"].lower()).ratio()
                if score >= TITLE_SIMILARITY_FLAG:
                    a["dup_of"] = r["v1_id"]
                    a["dup_basis"] = f"title similarity {score:.2f} to {r['title']!r}"
                    break


def attach_trovi(artifacts: list[dict]) -> tuple[int, int]:
    """Join the offline Trovi API dump onto the catalog, matched by title.

    trovi_records.json is a capture of the API that is otherwise unreachable.
    It supplies what the compendium cannot: the artifact UUID, authors, and the
    contents URN, which is the authoritative pointer to the artifact body.

    Two URN schemes appear:
      urn:trovi:contents:git:<url>@<sha>   a git repo pinned to a commit
      urn:trovi:contents:http:<uuid>       a Trovi-hosted blob, reachable only
                                           through the live API

    The second scheme is why the wrapper artifacts stay unfetchable: their body
    is not on GitHub at all, and the endpoint that would serve it is down.
    """
    for a in artifacts:
        a.update(trovi_uuid=None, trovi_authors=[], contents_urn=None,
                 contents_kind=None, contents_git_url=None, contents_sha=None)
    if not TROVI_RECORDS.exists():
        return 0, len(artifacts)

    recs = json.loads(TROVI_RECORDS.read_text(encoding="utf-8"))
    by_title = {r["title"].strip().lower(): r for r in recs if r.get("title")}
    matched = 0
    for a in artifacts:
        r = by_title.get(a["trovi_title"].strip().lower())
        if not r:
            continue
        matched += 1
        a["trovi_uuid"] = r.get("uuid")
        a["trovi_authors"] = [au.get("full_name") for au in (r.get("authors") or [])]
        versions = r.get("versions") or []
        urn = ""
        for v in versions:                       # last version wins
            urn = (v.get("contents") or {}).get("urn") or urn
        if not urn:
            continue
        a["contents_urn"] = urn
        parts = urn.split(":", 4)
        kind = parts[3] if len(parts) > 3 else None
        a["contents_kind"] = kind
        if kind == "git" and len(parts) > 4:
            body = parts[4]
            url, _, sha = body.rpartition("@")
            a["contents_git_url"] = url or body
            a["contents_sha"] = sha or None
    return matched, len(artifacts) - matched


def build() -> int:
    if not COMPENDIUM.exists():
        raise SystemExit(f"compendium not found at {COMPENDIUM}")
    artifacts = parse_compendium(COMPENDIUM)
    assign_ids(artifacts)
    matched, unmatched = attach_trovi(artifacts)
    v1 = load_v1_registry()
    apply_policy(artifacts, v1)

    CATALOG.write_text(
        "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in artifacts),
        encoding="utf-8")

    included = [a for a in artifacts if a["status"] == "included"]
    excluded = [a for a in artifacts if a["status"] == "excluded"]
    dups = [a for a in artifacts if a["dup_of"]]
    nourl = [a for a in artifacts if not a["repo_urls"]]

    print(f"[catalog] {len(artifacts)} artifacts parsed from compendium.txt")
    print(f"[catalog] {len(included)} included, {len(excluded)} excluded")
    print(f"[catalog] {sum(len(a['repo_urls']) for a in artifacts)} repo URLs, "
          f"{len(nourl)} artifacts with no URL")
    print(f"[catalog] v1 registry: {len(v1)} artifacts "
          f"({', '.join(r['v1_id'] for r in v1)})")
    kinds: dict[str, int] = {}
    for a in artifacts:
        kinds[a["contents_kind"] or "no-record"] = (
            kinds.get(a["contents_kind"] or "no-record", 0) + 1)
    print(f"[trovi] {matched} matched to trovi_records.json, {unmatched} unmatched; "
          f"contents kind {kinds}")
    if excluded:
        print("\nEXCLUDED:")
        for a in excluded:
            print(f"  {a['artifact_id']}\n      {a['exclusion_reason']}")
    if dups:
        print("\nNEAR-DUPLICATES OF v1 (flagged):")
        for a in dups:
            print(f"  {a['artifact_id']}  ->  {a['dup_of']}   [{a['status']}]")
            print(f"      {a['dup_basis']}")
    print(f"\n[written] {CATALOG.relative_to(WORKSPACE)}")
    return 0


def load_catalog() -> list[dict]:
    if not CATALOG.exists():
        raise SystemExit("catalog.jsonl missing. Run: catalog.py build")
    return [json.loads(l)
            for l in CATALOG.read_text(encoding="utf-8").splitlines() if l.strip()]


def show(artifact_id: str) -> int:
    for a in load_catalog():
        if a["artifact_id"] == artifact_id:
            print(json.dumps(a, indent=2, ensure_ascii=False))
            return 0
    print(f"no such artifact_id: {artifact_id}", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    s = sub.add_parser("show")
    s.add_argument("artifact_id")
    args = ap.parse_args()
    return build() if args.cmd == "build" else show(args.artifact_id)


if __name__ == "__main__":
    raise SystemExit(main())
