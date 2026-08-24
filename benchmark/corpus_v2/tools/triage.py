"""triage: classify every catalog artifact and write the audit manifest. Stage 2.

Three classes:

  instructional      tutorial or teaching material: the code exists to show how
                     to provision on Chameleon
  evidence           research artifact: provisioning code exists to run an
                     experiment and is incidental to the paper's claim
  no-chameleon-code  no Chameleon provisioning grammar anywhere in the repo

Classification is a scored vote across independent signals (Trovi tags, repo
owner, notebook shape, provisioning density), not a single rule. Every row
carries classification_reason naming the signals that fired, because a triage
decision that cannot be re-derived after the fact is not auditable.

triage_confidence is the normalized margin between the two competing scores. It
is low exactly when the instructional and evidence signals disagree, which is
what makes "lowest confidence" a meaningful phase 1 selection criterion rather
than an arbitrary one.

Output is TSV, not JSON: measured 57 tokens per row versus 238 for the
equivalent JSON entry, paid 200 times.

  python corpus_v2/tools/triage.py run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import load_catalog, normalize_repo  # noqa: E402
from detect import TriageSignals, scan_repo       # noqa: E402
from fetch import load_fetch_state, repo_dir      # noqa: E402

CORPUS = HERE.parent
BENCH = CORPUS.parent
WORKSPACE = BENCH.parent
MANIFEST = CORPUS / "manifest.tsv"

COLUMNS = ["artifact_id", "trovi_title", "repo_url", "fetch_status",
           "repo_size_mb", "triage_class", "triage_confidence",
           "matched_calls", "n_notebooks", "n_provisioning_cells",
           "provisioning_density", "n_fragments_predicted", "dispersed",
           "site_call_style", "api_family_detected", "python_chi_era",
           "total_bytes", "classification_reason"]

INSTRUCTIONAL_TAGS = {"education", "example", "experiment pattern", "appliance"}
EVIDENCE_TAGS = {"reproducible research"}
TEACHING_OWNERS = {"teaching-on-testbeds", "chameleoncloud"}

FETCHED = {"cloned", "sparse"}


def tsv_safe(value) -> str:
    """TSV has no quoting. Neutralize the delimiters instead of escaping them."""
    return (str(value).replace("\t", " ").replace("\r", " ")
            .replace("\n", " ").strip())


def pick_repos(artifact, state) -> list[tuple[str, dict]]:
    """(url, fetch record) for every successfully fetched repo of an artifact."""
    return [(u, state[u]) for u in artifact["repo_urls"]
            if state.get(u, {}).get("fetch_status") in FETCHED]


def merge_signals(sigs: list[TriageSignals]) -> TriageSignals:
    """Union the grammar across an artifact's repos, sum the shape counters.

    An artifact linking several repos is still one artifact. api_family and era
    collapse to 'mixed' when its repos disagree, which is itself a finding.
    """
    if not sigs:
        return TriageSignals()
    if len(sigs) == 1:
        return sigs[0]
    m = TriageSignals()
    m.matched_calls = sorted({c for s in sigs for c in s.matched_calls})
    m.imports = sorted({i for s in sigs for i in s.imports})
    m.n_notebooks = sum(s.n_notebooks for s in sigs)
    m.n_py = sum(s.n_py for s in sigs)
    m.n_code_units = sum(s.n_code_units for s in sigs)
    m.n_provisioning_cells = sum(s.n_provisioning_cells for s in sigs)
    m.n_fragments_predicted = sum(s.n_fragments_predicted for s in sigs)
    m.total_bytes = sum(s.total_bytes for s in sigs)
    m.strong_hits = max(s.strong_hits for s in sigs)
    m.weak_hits = max(s.weak_hits for s in sigs)
    m.provisioning_density = (round(m.n_provisioning_cells / m.n_code_units, 4)
                              if m.n_code_units else 0.0)
    m.dispersed = any(s.dispersed for s in sigs)

    def collapse(values, none_value):
        vals = {v for v in values if v != none_value}
        return none_value if not vals else (vals.pop() if len(vals) == 1 else "mixed")

    m.site_call_style = collapse((s.site_call_style for s in sigs), "none")
    m.api_family_detected = collapse((s.api_family_detected for s in sigs), "none")
    eras = {s.python_chi_era for s in sigs if s.python_chi_era != "unknown"}
    m.python_chi_era = ("unknown" if not eras else
                        (eras.pop() if len(eras) == 1 else "mixed"))
    return m


def classify(artifact, sig: TriageSignals, repos) -> tuple[str, float, str]:
    """(triage_class, triage_confidence, classification_reason)."""
    tags = {t.lower() for t in artifact["tags"]}
    owners = {normalize_repo(u).split("/")[0] for u in artifact["repo_urls"]}
    reasons: list[str] = []

    if not repos:
        return ("no-chameleon-code", 0.0,
                "no repo fetched, so the code was never inspected. Class is "
                "provisional and must not be counted as a verified negative.")

    # Absence of the grammar is decided first and on its own terms.
    if sig.strong_hits == 0 and not sig.imports:
        conf = 0.9 if sig.n_code_units >= 10 else 0.5 if sig.n_code_units >= 1 else 0.25
        reasons.append(f"zero strong provisioning calls and no chi-family import "
                       f"across {sig.n_code_units} code units "
                       f"({sig.n_notebooks} notebooks, {sig.n_py} py files)")
        if sig.n_code_units < 10:
            reasons.append("few code units, so absence is weakly evidenced")
        return "no-chameleon-code", conf, "; ".join(reasons)

    if sig.strong_hits == 0 and sig.imports:
        reasons.append(f"chi-family import {sig.imports} present but no strong "
                       f"provisioning call matched")

    i_score = e_score = 0
    if tags & INSTRUCTIONAL_TAGS:
        i_score += 2
        reasons.append(f"instructional tags {sorted(tags & INSTRUCTIONAL_TAGS)}")
    if owners & TEACHING_OWNERS:
        i_score += 2
        reasons.append(f"tutorial-publishing owner {sorted(owners & TEACHING_OWNERS)}")
    if sig.n_notebooks >= 1 and sig.provisioning_density >= 0.15:
        i_score += 1
        reasons.append(f"notebook-led with dense provisioning "
                       f"(density {sig.provisioning_density})")

    if tags & EVIDENCE_TAGS:
        e_score += 2
        reasons.append("tagged reproducible research")
    if "experiment" in tags:
        e_score += 1
        reasons.append("tagged experiment")
    if sig.provisioning_density < 0.10:
        e_score += 1
        reasons.append(f"sparse provisioning (density {sig.provisioning_density}), "
                       "typical of research code where setup is incidental")
    if sig.n_notebooks == 0:
        e_score += 1
        reasons.append("no notebooks, so not notebook-tutorial shaped")

    if i_score == e_score == 0:
        cls, conf = "evidence", 0.05
        reasons.append("no tag or owner signal either way; defaulted to evidence "
                       "as the lower-privilege class")
    else:
        cls = "instructional" if i_score > e_score else "evidence"
        conf = round(abs(i_score - e_score) / max(i_score + e_score, 1), 3)
    reasons.append(f"scores instructional={i_score} evidence={e_score}")
    return cls, conf, "; ".join(reasons)


def run() -> int:
    catalog = load_catalog()
    state = load_fetch_state()
    rows = []

    for a in catalog:
        repos = pick_repos(a, state)
        sigs = [scan_repo(repo_dir(rec["repo_key"])) for _u, rec in repos]
        sig = merge_signals(sigs)

        if a["status"] == "excluded":
            cls, conf = "excluded", 1.0
            reason = a["exclusion_reason"]
        else:
            cls, conf, reason = classify(a, sig, repos)

        if a["dup_of"]:
            reason += f"; NEAR-DUPLICATE of v1 {a['dup_of']} ({a['dup_basis']})"

        # Primary repo: most provisioning signal, then most code, then largest.
        if repos:
            order = sorted(range(len(repos)),
                           key=lambda i: (sigs[i].strong_hits,
                                          sigs[i].n_code_units,
                                          sigs[i].total_bytes), reverse=True)
            primary_url, primary_rec = repos[order[0]]
            if len(a["repo_urls"]) > 1:
                reason += (f"; artifact links {len(a['repo_urls'])} repos, "
                           f"signals merged, primary {primary_rec['repo_key']}")
        else:
            primary_url = a["repo_urls"][0] if a["repo_urls"] else ""
            primary_rec = state.get(primary_url, {})
            if primary_rec.get("error"):
                reason += f"; fetch error: {primary_rec['error']}"

        rows.append({
            "artifact_id": a["artifact_id"],
            "trovi_title": a["trovi_title"],
            "repo_url": primary_url,
            "fetch_status": primary_rec.get("fetch_status", "not_attempted"),
            "repo_size_mb": primary_rec.get("repo_size_mb") or "",
            "triage_class": cls,
            "triage_confidence": conf,
            "matched_calls": ";".join(sig.matched_calls),
            "n_notebooks": sig.n_notebooks,
            "n_provisioning_cells": sig.n_provisioning_cells,
            "provisioning_density": sig.provisioning_density,
            "n_fragments_predicted": sig.n_fragments_predicted,
            "dispersed": sig.dispersed,
            "site_call_style": sig.site_call_style,
            "api_family_detected": sig.api_family_detected,
            "python_chi_era": sig.python_chi_era,
            "total_bytes": sig.total_bytes,
            "classification_reason": reason,
        })

    MANIFEST.write_text(
        "\t".join(COLUMNS) + "\n"
        + "".join("\t".join(tsv_safe(r[c]) for c in COLUMNS) + "\n" for r in rows),
        encoding="utf-8")

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["triage_class"]] = counts.get(r["triage_class"], 0) + 1
    print(f"[triage] {len(rows)} artifacts written to "
          f"{MANIFEST.relative_to(WORKSPACE)}\n")
    print("TRIAGE CLASS COUNTS")
    for k in sorted(counts, key=lambda k: -counts[k]):
        print(f"  {k:20} {counts[k]:>4}")
    real_n = counts.get("instructional", 0) + counts.get("evidence", 0)
    print(f"\n  artifacts carrying Chameleon provisioning code: {real_n}")
    return 0


def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        raise SystemExit("manifest.tsv missing. Run: triage.py run")
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    return [dict(zip(header, l.split("\t"))) for l in lines[1:] if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run",))
    ap.parse_args()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
