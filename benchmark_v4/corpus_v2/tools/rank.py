"""rank: score every artifact by usefulness to the advisor, and export XLSX.

The advisor's goal is: given a use case, recommend appropriate resources. An
artifact is useful to that goal in proportion to how much of a *groundable
resource recommendation* can be pulled out of it deterministically.

That is a narrower question than "is this a good artifact". A well-cited paper
whose repo never names a node type is worth little here; a short tutorial that
says add_node_reservation(node_type="compute_skylake") on CHI@UC is worth a lot,
because the advisor can cite it when a user asks for a Skylake node.

So the score is built from what the emitter and validator actually need:

  resource literal   node_type / flavor / device. THE payload. Without it the
                     advisor has nothing concrete to recommend.        w 30
  site               which of the four sites. Governs everything downstream,
                     and per the as-built map must never be inferred.  w 15
  api_family         emitter and validator dispatch. A wrong value here is
                     risk R1, the loudest failure mode.                w 15
  workload legible   can we tell what the resource was FOR? A resource with no
                     use case attached cannot be matched to a query.   w 12
  spec surface       image, lease, network, storage.                   w 13
  extractability     dense, non-dispersed provisioning parses cleanly. w 8
  era                current API. Legacy-only artifacts must not be echoed
                     back to users as recommendations.                 w 4
  corroboration      Trovi access_count percentile. Weak signal, small weight,
                     included because a heavily used artifact is likelier to
                     be correct than an unused one.                    w 3

Two tag vocabularies are emitted, because the advisor performs a mapping and
needs both halves of it:

  workload_tags   what the user is trying to DO      (the query side)
  resource_tags   what that implies about hardware   (the answer side)

  python corpus_v2/tools/rank.py run
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from catalog import load_catalog                                  # noqa: E402
from detect import SKIP_DIRS, _notebook_cells, _strip_magics      # noqa: E402
from fetch import load_fetch_state, repo_dir                      # noqa: E402
from triage import load_manifest                                  # noqa: E402

CORPUS = HERE.parent
BENCH = CORPUS.parent
WORKSPACE = BENCH.parent
OUT = BENCH / "compendium" / "advisor_artifact_ranking.xlsx"
TROVI_RECORDS = BENCH / "compendium" / "trovi_records.json"

# ------------------------------------------------------------------ resources

SITE_RE = re.compile(r"\b(CHI@Edge|CHI@UC|CHI@TACC|KVM@TACC)\b", re.I)
NODE_TYPE_RE = re.compile(
    r"\b(compute_(?:skylake|cascadelake(?:_r)?|haswell|icelake_r|zen3|liqid)"
    r"|storage(?:_hierarchy|_nvme)?|gpu_(?:rtx_6000|v100|a100|p100|k80|m40|mi100)"
    r"|fpga_\w+|compute_nvdimm|raspberrypi\d?-?\d*|jetson-?\w*|xavier|orin)\b", re.I)
GPU_RE = re.compile(
    r"\b(A100|H100|V100|P100|K80|M40|RTX\s?6000|RTX\s?A6000|T4|L40S?|MI100|MI250"
    r"|GTX\s?\d{3,4})\b", re.I)
FLAVOR_RE = re.compile(r"\b(m1\.\w+|g1\.\w+|gpu\.\w+)\b")

RESOURCE_KWARGS = {
    "node_type": {"node_type"},
    "device": {"machine_type", "machine_name"},
    "flavor": {"flavor_name", "flavor", "flavor_id"},
    "image": {"image_ref", "image", "image_name"},
    "count": {"count", "amount", "node_count"},
}
LEASE_KWARGS = {"hours", "days", "minutes"}
SCAN_SUFFIXES = (".py", ".ipynb", ".md", ".sh", ".yaml", ".yml")


def _const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float)):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values
                       if isinstance(v, ast.Constant) and isinstance(v.value, str))
    return None


def _blank_res() -> dict:
    r = {k: set() for k in RESOURCE_KWARGS}
    r.update(site=set(), lease_hours=set(), gpus=set(), node_vocab=set(),
             flavor_vocab=set(), has_fip=False, has_storage=False,
             has_multinode=False)
    return r


def extract_resources(root: Path) -> dict:
    """Resource literals from AST kwargs, widened by a vocabulary sweep.

    AST gives precision (a real kwarg on a real call); the regex sweep gives
    recall over prose, shell cells, and values the AST cannot resolve. Both are
    kept separately, and only AST-observed literals earn full credit, because
    the schema doc is explicit that node_type and site are never inferred.
    """
    out = _blank_res()
    if not root.exists():
        return out

    texts: list[tuple[str, bool]] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        if SKIP_DIRS & set(p.relative_to(root).parts):
            continue
        if p.suffix not in SCAN_SUFFIXES:
            continue
        try:
            if p.stat().st_size > 20_000_000:
                continue
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if p.suffix == ".ipynb":
            for c in _notebook_cells(p):
                texts.append((c, True))
            texts.append((raw[:400_000], False))   # markdown cells and prose
        else:
            texts.append((raw, p.suffix in (".py", ".sh")))

    for src, is_code in texts:
        for m in SITE_RE.finditer(src):
            out["site"].add(m.group(1))
        for m in NODE_TYPE_RE.finditer(src):
            out["node_vocab"].add(m.group(1).lower())
        for m in GPU_RE.finditer(src):
            out["gpus"].add(re.sub(r"\s+", " ", m.group(1)).upper())
        for m in FLAVOR_RE.finditer(src):
            out["flavor_vocab"].add(m.group(1))
        if re.search(r"associate_floating_ip|floating_ip|add_fip_reservation", src):
            out["has_fip"] = True
        if re.search(r"attach_volume|object_store|swift|cinder|manila|\bs3\b",
                     src, re.I):
            out["has_storage"] = True
        if not is_code:
            continue
        try:
            tree = ast.parse(_strip_magics(src))
        except (SyntaxError, ValueError, RecursionError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = (node.func.attr if isinstance(node.func, ast.Attribute)
                  else node.func.id if isinstance(node.func, ast.Name) else "")
            for kw in node.keywords:
                if kw.arg is None:
                    continue
                val = _const(kw.value)
                if val is None:
                    continue
                if isinstance(val, str) and val.strip():
                    for field, names in RESOURCE_KWARGS.items():
                        if kw.arg in names:
                            out[field].add(val.strip())
                if kw.arg in LEASE_KWARGS and isinstance(val, (int, float)):
                    hours = (val * 24 if kw.arg == "days"
                             else val / 60 if kw.arg == "minutes" else val)
                    out["lease_hours"].add(round(float(hours), 2))
                if kw.arg in RESOURCE_KWARGS["count"] and isinstance(val, int) \
                        and not isinstance(val, bool) and val > 1:
                    out["has_multinode"] = True
            if fn in ("use_site", "choose_site") and node.args:
                v = _const(node.args[0])
                if isinstance(v, str) and v.strip():
                    out["site"].add(v.strip())
    return out


# ------------------------------------------------------------------- taxonomy
# workload_tags answer "what is the user trying to do", the query side of the
# mapping the advisor performs. Matched over title, Trovi descriptions, and
# repo text, so they fire on prose as well as code.

WORKLOAD_TAGS: dict[str, tuple[str, str]] = {
    "llm-training": (r"\b(llm|large language model|gpt|llama|transformer)\b.{0,40}\b(train|finetun|fine-tun|pretrain)|fine-?tun\w*.{0,30}\bllm\b", "Training or fine-tuning large language models"),
    "llm-serving": (r"\bvllm\b|tensorrt-?llm|text-generation-inference|\b(llm|language model)\b.{0,30}\b(serv|infer|deploy)", "Serving or inference for large language models"),
    "ml-training": (r"\btrain\w*\b.{0,40}\b(model|network|neural|cnn|resnet|bert)|\bmodel training\b|\btraining job\b", "General machine-learning model training"),
    "ml-inference": (r"\binference\b|\bmodel serving\b|\bserving\b.{0,20}\bmodel\b", "Inference or model serving"),
    "computer-vision": (r"\b(image classif\w*|object detect\w*|segmentation|computer vision|cnn|resnet|yolo|opencv)\b", "Computer-vision workloads"),
    "nlp": (r"\b(nlp|natural language|text classif\w*|sentiment|tokeniz\w*|machine translation)\b", "Natural-language processing"),
    "distributed-training": (r"\b(distributed training|data parallel|model parallel|deepspeed|horovod|fsdp|multi-?gpu|multi-?node)\b", "Training spread across multiple GPUs or nodes"),
    "mlops": (r"\b(mlflow|experiment tracking|model registry|kubeflow|wandb|weights ?& ?biases)\b", "ML lifecycle, tracking, and orchestration"),
    "big-data": (r"\b(spark|hadoop|hdfs|mapreduce|etl\b|data pipeline)\b", "Large-scale data processing"),
    "databases": (r"\b(database|postgres|mysql|cassandra|rocksdb|lsm-?tree|key-?value store|oltp|\bsql\b)\b", "Database and storage-engine research"),
    "storage-systems": (r"\b(file ?system|erasure cod\w*|flash cache|nvme|block storage|object storage|ceph)\b", "Storage systems and filesystems"),
    "networking": (r"\b(sdn|openflow|network emulation|rdma|packet|switch\w*|routing|bandwidth|congestion)\b", "Networking and SDN"),
    "kernel-os": (r"\b(kernel|scheduler|ebpf|\bbpf\b|syscall|operating system|hypervisor|virtualiz\w*)\b", "Kernel and OS research"),
    "distributed-systems": (r"\b(consensus|raft|paxos|blockchain|permissioned|replication|fault toler\w*|microservice)\b", "Distributed systems and consensus"),
    "security-fuzzing": (r"\b(fuzz\w*|vulnerabilit\w*|exploit|security|malware|intrusion|adversarial)\b", "Security, fuzzing, and adversarial work"),
    "formal-verification": (r"\b(verif\w*|theorem prov\w*|model check\w*|\bsmt\b|static analys\w*)\b", "Formal verification and program analysis"),
    "hpc-simulation": (r"\b(\bmpi\b|\bhpc\b|finite element|\bcfd\b|simulation|numerical|solver|molecular dynamics|galerkin)\b", "HPC and numerical simulation"),
    "edge-iot": (r"\b(edge device|\biot\b|sensor|gpio|raspberry|jetson|camera|peripheral|sense ?hat)\b", "Edge devices, sensors, and IoT"),
    "containers-k8s": (r"\b(kubernetes|k8s|docker|container orchestration|helm|operator)\b", "Containers and orchestration"),
    "compilers": (r"\b(compiler|llvm|\bjit\b|wasm|webassembly|instruction select\w*|code ?gen\w*)\b", "Compilers and code generation"),
    "reproducibility": (r"\b(reproduc\w*|artifact evaluation|replicat\w*|repeatab\w*)\b", "Reproducibility and artifact evaluation"),
    "teaching": (r"\b(tutorial|course|lesson|classroom|teaching|getting started|hands-?on|walkthrough)\b", "Teaching and tutorial material"),
    "benchmarking": (r"\b(benchmark\w*|throughput|profil\w*|speedup|overhead)\b", "Benchmarking and performance measurement"),
}

# resource_tags answer "what hardware does that imply", the answer side. These
# come from observed resources and code signals, never from prose alone,
# because this half is what the advisor emits and must not be guessed.
RESOURCE_TAG_DEFS = {
    "gpu-required": "A GPU model or gpu_* node type is named in the artifact",
    "multi-gpu": "More than one distinct GPU model named, or an explicit multi-GPU signal",
    "cpu-only": "Provisioning present but no GPU named anywhere",
    "bare-metal": "Baremetal grammar present (add_node_reservation / create_server)",
    "kvm-vm": "KVM grammar present (add_flavor_reservation / get_flavor_id)",
    "edge-device": "Edge grammar present (add_device_reservation / Container)",
    "multi-node": "A reservation count or amount greater than 1",
    "public-network": "Floating IP association or FIP reservation",
    "persistent-storage": "Volume, object store, or S3/Swift/Cinder usage",
    "long-lease": "A declared lease of 24 hours or more",
    "short-lease": "A declared lease under 24 hours",
    "fpga": "An FPGA node type is named",
    "arm-arch": "An ARM, Raspberry Pi, or Jetson node type is named",
}

TIERS = [(70, "A", "directly groundable: site, family, and a concrete resource"),
         (45, "B", "usable with review: partial resource specification"),
         (20, "C", "weak: provisioning present but little resource detail"),
         (0, "D", "not useful for resource recommendation")]


def workload_tags(text: str) -> list[str]:
    return [name for name, (pat, _d) in WORKLOAD_TAGS.items()
            if re.search(pat, text, re.I)]


def resource_tags(res: dict, fam: str) -> list[str]:
    tags = []
    if res["gpus"] or any("gpu" in n for n in res["node_vocab"]):
        tags.append("gpu-required")
        if len(res["gpus"]) > 1:
            tags.append("multi-gpu")
    else:
        tags.append("cpu-only")
    if fam in ("baremetal", "mixed"):
        tags.append("bare-metal")
    if fam in ("kvm", "mixed"):
        tags.append("kvm-vm")
    if fam == "edge":
        tags.append("edge-device")
    if res["has_multinode"]:
        tags.append("multi-node")
    if res["has_fip"]:
        tags.append("public-network")
    if res["has_storage"]:
        tags.append("persistent-storage")
    if res["lease_hours"]:
        tags.append("long-lease" if max(res["lease_hours"]) >= 24 else "short-lease")
    if any("fpga" in n for n in res["node_vocab"]):
        tags.append("fpga")
    if any(re.search(r"raspberry|jetson|xavier|orin", n) for n in res["node_vocab"]):
        tags.append("arm-arch")
    return tags


def score(row, res, wtags, access_pct) -> tuple[float, str]:
    """Weighted score plus the justification, so a rank can be argued with."""
    if row["triage_class"] in ("no-chameleon-code", "excluded"):
        return 0.0, ("no Chameleon provisioning code, so there is nothing for the "
                     "advisor to ground a resource recommendation on")
    pts, why = 0.0, []

    kwarg_res = res["node_type"] | res["device"] | res["flavor"]
    text_res = res["node_vocab"] | res["flavor_vocab"]
    if kwarg_res:
        pts += 30
        why.append(f"resource literal observed as a call kwarg: "
                   f"{sorted(kwarg_res)[:3]} (+30)")
    elif text_res:
        pts += 15
        why.append(f"resource named in text only, not as a kwarg: "
                   f"{sorted(text_res)[:3]} (+15)")
    else:
        why.append("no concrete node_type or flavor anywhere (+0)")

    if res["site"]:
        pts += 15
        why.append(f"site {sorted(res['site'])} declared (+15)")
    else:
        why.append("no site literal (+0)")

    fam = row["api_family_detected"]
    if fam in ("edge", "kvm", "baremetal"):
        pts += 15
        why.append(f"api_family {fam} unambiguous (+15)")
    elif fam == "mixed":
        pts += 7
        why.append("api_family mixed, needs disambiguation (+7)")
    else:
        why.append("api_family absent, emitter cannot dispatch (+0)")

    if wtags:
        w = min(12.0, 4.0 * len(wtags))
        pts += w
        why.append(f"workload legible: {', '.join(wtags[:4])} (+{w:g})")
    else:
        why.append("no workload signal, cannot match to a query (+0)")

    spec = 0.0
    if res["image"]:
        spec += 4
        why.append("image declared (+4)")
    if res["lease_hours"]:
        spec += 4
        why.append(f"lease {sorted(res['lease_hours'])[:3]} h declared (+4)")
    if res["has_fip"]:
        spec += 2.5
        why.append("network config present (+2.5)")
    if res["has_storage"]:
        spec += 2.5
        why.append("storage config present (+2.5)")
    pts += spec

    dens = float(row["provisioning_density"] or 0)
    ext = (8.0 if dens >= 0.15 and row["dispersed"] != "True"
           else 4.0 if dens >= 0.05 else 1.0)
    pts += ext
    why.append(f"extractability density={dens} dispersed={row['dispersed']} (+{ext:g})")

    era = row["python_chi_era"]
    e = 4.0 if era == "current" else 2.0 if era == "mixed" else 0.0
    pts += e
    why.append(f"python_chi_era {era} (+{e:g})")

    c = round(3.0 * access_pct, 1)
    pts += c
    why.append(f"Trovi access percentile {access_pct:.2f} (+{c:g})")
    return round(min(pts, 100.0), 1), "; ".join(why)


def tier_for(s: float) -> str:
    for cut, name, _desc in TIERS:
        if s >= cut:
            return name
    return "D"


def run() -> int:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    manifest = load_manifest()
    catalog = {a["artifact_id"]: a for a in load_catalog()}
    state = load_fetch_state()

    phases = {}
    pf = CORPUS / "phases.tsv"
    if pf.exists():
        lines = pf.read_text(encoding="utf-8").splitlines()
        hdr = lines[0].split("\t")
        for l in lines[1:]:
            if l.strip():
                d = dict(zip(hdr, l.split("\t")))
                phases[d["artifact_id"]] = d["phase"]

    trovi = {}
    if TROVI_RECORDS.exists():
        for r in json.loads(TROVI_RECORDS.read_text(encoding="utf-8")):
            if r.get("title"):
                trovi[r["title"].strip().lower()] = r
    accesses = sorted((r.get("metrics") or {}).get("access_count", 0)
                      for r in trovi.values())

    def pct(v):
        return (sum(1 for a in accesses if a < v) / len(accesses)) if accesses else 0.0

    # One scan per repo, shared across the artifacts that link it.
    cache: dict[str, dict] = {}
    rows = []
    for m in manifest:
        aid = m["artifact_id"]
        cat = catalog.get(aid, {})
        rec = trovi.get(m["trovi_title"].strip().lower(), {})
        desc = " ".join([m["trovi_title"], rec.get("short_description") or "",
                         rec.get("long_description") or "",
                         " ".join(cat.get("tags") or [])])

        res = _blank_res()
        for u in cat.get("repo_urls", []):
            r = state.get(u, {})
            if r.get("fetch_status") not in ("cloned", "sparse"):
                continue
            key = r["repo_key"]
            if key not in cache:
                cache[key] = extract_resources(repo_dir(key))
            for k, v in cache[key].items():
                if isinstance(v, set):
                    res[k] |= v
                elif v:
                    res[k] = True

        wt = workload_tags(desc)
        rt = (resource_tags(res, m["api_family_detected"])
              if m["triage_class"] in ("instructional", "evidence") else [])
        ac = (rec.get("metrics") or {}).get("access_count", 0)
        s, why = score(m, res, wt, pct(ac))

        rows.append({
            "advisor_score": s, "tier": tier_for(s), "artifact_id": aid,
            "trovi_title": m["trovi_title"], "triage_class": m["triage_class"],
            "api_family_detected": m["api_family_detected"],
            "site_observed": "; ".join(sorted(res["site"])),
            "node_types_observed": "; ".join(
                sorted(res["node_type"] | res["device"] | res["node_vocab"])[:8]),
            "flavors_observed": "; ".join(
                sorted(res["flavor"] | res["flavor_vocab"])[:6]),
            "gpus_mentioned": "; ".join(sorted(res["gpus"])[:6]),
            "image_observed": "; ".join(sorted(res["image"])[:3]),
            "lease_hours_declared": "; ".join(
                str(x) for x in sorted(res["lease_hours"])[:5]),
            "workload_tags": "; ".join(wt), "resource_tags": "; ".join(rt),
            "trovi_tags": "; ".join(cat.get("tags") or []),
            "python_chi_era": m["python_chi_era"],
            "site_call_style": m["site_call_style"],
            "n_provisioning_cells": int(m["n_provisioning_cells"] or 0),
            "provisioning_density": float(m["provisioning_density"] or 0),
            "dispersed": m["dispersed"], "phase": phases.get(aid, ""),
            "access_count": ac, "repo_url": m["repo_url"],
            "trovi_uuid": cat.get("trovi_uuid") or "", "why_ranked": why,
        })

    rows.sort(key=lambda r: (-r["advisor_score"], r["artifact_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    wb = Workbook()
    hdr_font = Font(bold=True, color="FFFFFF")
    hdr_fill = PatternFill("solid", fgColor="1F4E79")
    tier_fill = {"A": "C6EFCE", "B": "FFEB9C", "C": "FCE4D6", "D": "F2F2F2"}

    def sheet(ws, cols, data, widths=None):
        ws.append(cols)
        for c in range(1, len(cols) + 1):
            cell = ws.cell(row=1, column=c)
            cell.font, cell.fill = hdr_font, hdr_fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for d in data:
            ws.append([d.get(c, "") for c in cols])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for idx, c in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(idx)].width = (
                (widths or {}).get(c, min(max(12, len(c) + 2), 40)))

    ws = wb.active
    ws.title = "Ranked Artifacts"
    cols = ["rank", "advisor_score", "tier", "artifact_id", "trovi_title",
            "triage_class", "api_family_detected", "site_observed",
            "node_types_observed", "flavors_observed", "gpus_mentioned",
            "image_observed", "lease_hours_declared", "workload_tags",
            "resource_tags", "trovi_tags", "python_chi_era", "site_call_style",
            "n_provisioning_cells", "provisioning_density", "dispersed",
            "phase", "access_count", "repo_url", "trovi_uuid", "why_ranked"]
    sheet(ws, cols, rows, widths={"trovi_title": 46, "why_ranked": 100,
                                  "workload_tags": 34, "resource_tags": 30,
                                  "node_types_observed": 30, "repo_url": 46,
                                  "artifact_id": 38, "trovi_uuid": 36,
                                  "trovi_tags": 26, "gpus_mentioned": 18})
    for i in range(2, len(rows) + 2):
        c = ws.cell(row=i, column=3)
        c.fill = PatternFill("solid", fgColor=tier_fill.get(c.value, "F2F2F2"))

    wtc: dict[str, int] = {}
    for r in rows:
        for t in (r["workload_tags"].split("; ") if r["workload_tags"] else []):
            wtc[t] = wtc.get(t, 0) + 1
    sheet(wb.create_sheet("Workload Tags"),
          ["tag", "definition", "artifacts", "tier_A_or_B", "advisor_role"],
          [{"tag": k, "definition": v[1], "artifacts": wtc.get(k, 0),
            "tier_A_or_B": sum(1 for r in rows if k in r["workload_tags"].split("; ")
                               and r["tier"] in ("A", "B")),
            "advisor_role": "query side: matches what the user asks for"}
           for k, v in sorted(WORKLOAD_TAGS.items(), key=lambda x: -wtc.get(x[0], 0))],
          widths={"definition": 58, "advisor_role": 44, "tag": 24})

    rtc: dict[str, int] = {}
    for r in rows:
        for t in (r["resource_tags"].split("; ") if r["resource_tags"] else []):
            rtc[t] = rtc.get(t, 0) + 1
    sheet(wb.create_sheet("Resource Tags"),
          ["tag", "definition", "artifacts", "advisor_role"],
          [{"tag": k, "definition": v, "artifacts": rtc.get(k, 0),
            "advisor_role": "answer side: what the advisor emits"}
           for k, v in sorted(RESOURCE_TAG_DEFS.items(),
                              key=lambda x: -rtc.get(x[0], 0))],
          widths={"definition": 64, "advisor_role": 40, "tag": 22})

    rubric = [
        ("resource literal", 30, "node_type / flavor / device. THE payload: without it there is nothing concrete to recommend. Full credit only when observed as a call kwarg, half when named in text only, because the schema is explicit that these are never inferred."),
        ("site", 15, "Which of the four sites. Governs everything downstream and must never be inferred."),
        ("api_family", 15, "Emitter and validator dispatch. A wrong value here is risk R1, a spec that fails at submission. mixed scores half."),
        ("workload legibility", 12, "Can we tell what the resource was FOR. A resource with no use case attached cannot be matched to a query. 4 points per workload tag, capped at 12."),
        ("spec surface", 13, "image (+4), lease duration (+4), network (+2.5), storage (+2.5)."),
        ("extractability", 8, "Dense, non-dispersed provisioning parses cleanly. Dispersed code breaks the fragment boundary heuristic."),
        ("python_chi_era", 4, "current +4, mixed +2, legacy 0. Deprecated calls must not be echoed back to users as recommendations."),
        ("corroboration", 3, "Trovi access_count percentile. Deliberately small: popularity is weak evidence of correctness."),
    ]
    sheet(wb.create_sheet("Scoring Rubric"), ["component", "max_points", "rationale"],
          [{"component": a, "max_points": b, "rationale": c} for a, b, c in rubric],
          widths={"rationale": 105, "component": 24})
    ws4 = wb["Scoring Rubric"]
    ws4.append([])
    ws4.append(["tier", "cutoff", "meaning"])
    for cut, name, desc in TIERS:
        ws4.append([name, f">= {cut}", desc])

    def tally(key):
        d: dict = {}
        for r in rows:
            d[r[key]] = d.get(r[key], 0) + 1
        return d
    summary = []
    for label in ("tier", "triage_class", "api_family_detected", "python_chi_era"):
        for k, v in sorted(tally(label).items(), key=lambda x: -x[1]):
            summary.append({"dimension": label, "value": k, "artifacts": v})
    sheet(wb.create_sheet("Summary"), ["dimension", "value", "artifacts"], summary,
          widths={"dimension": 24, "value": 28})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)

    print(f"[rank] {len(rows)} artifacts scored -> {OUT.relative_to(WORKSPACE)}\n")
    print("TIER DISTRIBUTION")
    for cut, name, desc in TIERS:
        n = sum(1 for r in rows if r["tier"] == name)
        print(f"  {name}  {n:>4}   {desc}")
    print("\nTOP 15 BY ADVISOR SCORE")
    for r in rows[:15]:
        print(f"  {r['advisor_score']:>5} {r['tier']} {r['artifact_id'][:40]:42} "
              f"{r['api_family_detected']:10} {r['site_observed'][:22]:24} "
              f"{r['workload_tags'][:34]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("run",))
    ap.parse_args()
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
