"""
Computed tier assignment (decision D04/D14).

For each item and each declared fed_set, measure key-token coverage against the
concatenated grounding files of the fed artifacts:

  mechanism tokens : API function names the gold depends on
  specifics tokens : magic strings (images, profiles, device names, commands)
  adapted tokens   : values deliberately changed from the source artifact (T2 design)

Rules (relative to a non-empty fed set):
  T1  mech=1.0, spec=1.0, adapted all ABSENT-list empty (nothing adapted) or present,
      and one single fed artifact alone covers everything
  T2  mech=1.0, spec=1.0, item declares adapted tokens and >=1 is absent from context
  T3  mech=1.0, spec=1.0, but NO single fed artifact alone covers everything
  T4  any mechanism or specifics token absent from every fed artifact

Writes exports/tier_report.json and prints a table. Mismatches between computed
tier and the item's tier_intent are flagged (they bounce back to the author).
"""

import json
import sys

import yaml

from chi_edge_bench.paths import exports_dir, grounding_dir, items_dir


def _load_grounding():
    g = {}
    for p in grounding_dir().glob("A*.md"):
        g[p.stem] = p.read_text()
    return g


def coverage(tokens, text):
    if not tokens:
        return 1.0, []
    missing = [t for t in tokens if t not in text]
    return 1 - len(missing) / len(tokens), missing


def assign(item, fed, grounding):
    if not fed:
        return {"tier": "blind", "detail": "no fed artifacts"}
    text = "\n".join(grounding[a] for a in fed)
    kt = item.get("key_tokens", {})
    mech_cov, mech_miss = coverage(kt.get("mechanism", []), text)
    spec_cov, spec_miss = coverage(kt.get("specifics", []), text)
    adapted = kt.get("adapted", [])
    _, adapted_miss = coverage(adapted, text)
    if mech_cov < 1.0 or spec_cov < 1.0:
        return {"tier": "T4", "missing": mech_miss + spec_miss,
                "mech_cov": mech_cov, "spec_cov": spec_cov}
    if adapted and adapted_miss:
        return {"tier": "T2", "adapted_absent": adapted_miss}
    single = any(
        coverage(kt.get("mechanism", []), grounding[a])[0] == 1.0
        and coverage(kt.get("specifics", []), grounding[a])[0] == 1.0
        for a in fed)
    return {"tier": "T1" if single else "T3",
            "single_artifact_covers": single}


def main():
    # exports/tier_report.json is the cited core artifact. Only a core run may
    # claim that filename; anything wider writes tier_report_<suite>.json.
    suite = "all"
    for i, a in enumerate(sys.argv):
        if a == "--suite" and i + 1 < len(sys.argv):
            suite = sys.argv[i + 1]

    grounding = _load_grounding()
    rows, mismatches = [], []
    for p in sorted(items_dir().glob("*.yaml")):
        item = yaml.safe_load(p.read_text())
        # Items predating v5 carry no `suite` key; they are the core suite.
        if suite != "all" and item.get("suite", "core") != suite:
            continue
        for cond, fed in item.get("fed_sets", {}).items():
            res = assign(item, fed, grounding)
            row = {"item": item["id"], "condition": cond, "fed": fed, **res}
            rows.append(row)
            intent = item.get("tier_intent_by_condition", {}).get(cond)
            if intent and res["tier"] != intent:
                mismatches.append(row | {"intended": intent})
    out = exports_dir() / ("tier_report.json" if suite == "core"
                           else f"tier_report_{suite}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"rows": rows, "mismatches": mismatches}, indent=2))
    for r in rows:
        flag = ""
        for m in mismatches:
            if m["item"] == r["item"] and m["condition"] == r["condition"]:
                flag = f"  <-- MISMATCH (intended {m['intended']})"
        print(f"{r['item']:<6} {r['condition']:<8} fed={','.join(r['fed']) or '-':<14} "
              f"-> {r['tier']}{flag}")
    print(f"\n{len(rows)} (item, condition) pairs; {len(mismatches)} mismatches "
          f"-> {out.relative_to(ROOT)}")
    sys.exit(1 if mismatches else 0)


if __name__ == "__main__":
    main()
