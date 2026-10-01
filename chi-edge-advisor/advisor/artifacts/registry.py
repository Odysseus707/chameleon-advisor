"""Registry of Trovi artifacts across the whole Chameleon testbed.

Each artifact is one independently-retrievable namespace (keyed by
``artifact_id``). Metadata here is the routing signal; the prose lives in the
grounding files.

TWO POPULATIONS, ONE REGISTRY.

  EDGE (5)     Hand-written below, keyed by repo slug, grounding in a directory
               per artifact under ``settings.grounding_dir``. These predate the
               corpus and their routing feeds already-collected benchmark
               answers, so they are frozen: do not edit the literals.

  CHAMELEON    Loaded from ``settings.corpus_dir/artifacts/A*.yaml``, keyed by
  (90)         benchmark A-id, grounding a single ``grounding/A*.md`` file read
               IN PLACE. The benchmark owns this data. Copying it here would
               recreate the advisor/benchmark drift the loader exists to
               prevent, so the loader reads and never writes.

MAPPING RULES for the chameleon records. Every one is a judgment call and a
reader is entitled to see which:

  site          First of ``site_observed``, tiebroken toward the entry matching
                ``api_family`` (a KVM@ site when api_family is kvm). Primary
                only; ``sites`` carries the rest.
  sites         All of ``site_observed``. RouterTree branches on this, so a
                two-site artifact appears in both branches with ONE store
                namespace - no duplicated grounding, and provenance keeps
                naming an id the benchmark can resolve.
  (no site)     2 artifacts observe no site at all. They are loaded but carry
                an empty ``sites``, which keeps them out of every RouterTree
                branch. Defaulting them into a site would be a guess, and
                recommending hardware at the wrong site is wrong in a way no
                amount of waiting fixes.
  api_family    Verbatim when baremetal/kvm. 25 records say "none" and 3 say
                "mixed"; those are DERIVED from the resolved site (KVM@ -> kvm,
                else baremetal) and flagged in ``api_family_source`` so a
                derived value is never read as an observed one.
  tags          ``retrieval_tags`` when authored - true for only 22 of 90, and
                that is the honest ceiling on tag-routing quality for this
                wing. The other 68 fall back to workload_tags + resource_tags +
                node_types_observed, which is weaker signal; ``tags_source``
                records which.
  node_types    ``node_types_observed`` filtered to types the capability table
                actually knows. The raw field carries "xavier" and
                "raspberrypi-" from an extraction regex; 9 of the 29 real types
                appear, the other 20 are named by no artifact at all.
  flavors       ``flavors_observed`` filtered to the real flavor set. The raw
                field is polluted by the same regex catching filenames and
                attribute lookups - "gpu.ipynb", "gpu.svg", "gpu.lower",
                "m1.addressable_shards" all appear as if they were flavors.

Capability NEVER comes from an artifact. An artifact may say a node type
exists; what that hardware can do is the capability table's business alone.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from ..config import settings

log = logging.getLogger(__name__)


@dataclass
class ArtifactMeta:
    artifact_id: str
    repo: str
    title: str
    # routing/grounding facts
    machine_types: List[str]
    device_profiles: List[str]
    image: str
    architecture: str
    gpu: bool
    # keywords used by the router's task classifier
    tags: List[str] = field(default_factory=list)
    # subdirectory under grounding_dir (defaults to artifact_id)
    subdir: str = ""
    # logical partition keys for RouterTree (site -> use_case -> artifact)
    site: str = "CHI@Edge"
    # empty use_case means the artifact is its own use-case
    use_case: str = ""

    # -- chameleon wing. Every default reproduces the edge shape, so the five
    # frozen entries above are unaffected by their existence.
    sites: List[str] = field(default_factory=list)
    node_types: List[str] = field(default_factory=list)
    flavors: List[str] = field(default_factory=list)
    api_family: str = "edge"
    workload_tags: List[str] = field(default_factory=list)
    content_group: str = ""
    # Single grounding file, when the artifact has one instead of a directory.
    grounding_file: Optional[Path] = None
    # Provenance for the two fields that are sometimes derived rather than
    # observed. Never let a derived value be read as a measured one.
    tags_source: str = "authored"       # authored | fallback
    api_family_source: str = "observed"  # observed | derived_from_site
    # Which population this record belongs to. Load-bearing: see branch_sites.
    wing: str = "edge"                  # edge | chameleon

    def dir(self) -> Path:
        return settings.grounding_dir / (self.subdir or self.artifact_id)

    def branch_sites(self) -> List[str]:
        """Sites this artifact should appear under in RouterTree.

        Empty is a real answer: an artifact that observed no site does not
        belong in a branch, and must not be defaulted into one.

        THE CHI@Edge BRANCH IS CLOSED to the five frozen entries. Two corpus
        artifacts genuinely observe CHI@Edge (A83 is an edge model-serving
        tutorial, A52 an all-sites benchmarking harness), and admitting them
        measurably moves edge routing: A83 alone takes a top-3 slot away from
        the correct artifact on 15 of 93 covered edge items, dropping L2 from
        93.5% to 77.4%. The edge wing's routing feeds 3231 already-collected
        answer cells, so that is a regression against published numbers, not an
        improvement. They keep their non-edge branches and simply do not
        compete on a wing that is frozen.
        """
        sites = self.sites or ([self.site] if self.site else [])
        if self.wing != "edge":
            sites = [s for s in sites if s != "CHI@Edge"]
        return list(sites)


# Seed set requested for the prototype. Facts are taken verbatim from each
# artifact's grounded notebook (see grounding/<id>/).
#
# FROZEN. These five feed already-collected benchmark answers; changing a tag
# here moves routing that published numbers depend on.
EDGE_ARTIFACTS: List[ArtifactMeta] = [
    ArtifactMeta(
        artifact_id="edge_ssh_image",
        repo="github.com/ChameleonCloud/edge_ssh_image",
        title="SSH on CHI@Edge containers",
        machine_types=["raspberrypi4-64"],
        device_profiles=[],
        image="ghcr.io/chameleoncloud/edge_ssh_image:latest",
        architecture="arm64",
        gpu=False,
        tags=[
            "ssh", "remote access", "interactive shell", "login", "ubuntu",
            "networking", "floating ip", "port 22", "sshd", "terminal",
        ],
        use_case="access",
    ),
    ArtifactMeta(
        artifact_id="edge-picamera-image",
        repo="github.com/ChameleonCloud/edge-picamera-image",
        title="Pi Camera Module 3 on CHI@Edge",
        machine_types=["raspberrypi4-64"],
        device_profiles=["pi_libcamera"],
        image="ghcr.io/chameleoncloud/edge-picamera-image:latest",
        architecture="arm64",
        gpu=False,
        tags=[
            "camera", "picamera", "libcamera", "photo", "image capture",
            "video", "h264", "rpicam", "vision", "still", "recording",
        ],
        use_case="peripherals",
    ),
    ArtifactMeta(
        artifact_id="edge_sensehat_image",
        repo="github.com/ChameleonCloud/edge_sensehat_image",
        title="Sense HAT sensors on CHI@Edge",
        machine_types=["raspberrypi4-64"],
        device_profiles=["pi_sensehat", "pi_gpio"],
        image="ghcr.io/chameleoncloud/edge_sensehat_image:latest",
        architecture="arm64",
        gpu=False,
        tags=[
            "sensor", "sense hat", "temperature", "humidity", "pressure",
            "barometric", "imu", "accelerometer", "gyroscope", "magnetometer",
            "i2c", "gpio", "environmental", "waveshare", "adc",
        ],
        use_case="peripherals",
    ),
    ArtifactMeta(
        artifact_id="edge-cpu-inference",
        repo="github.com/teaching-on-testbeds/edge-cpu-inference",
        title="CPU-based ML inference on CHI@Edge",
        machine_types=["raspberrypi4-64"],
        device_profiles=[],
        image="python:3.9-slim",
        architecture="arm64",
        gpu=False,
        tags=[
            "inference", "machine learning", "ml", "model", "cpu",
            "image classification", "mobilenet", "tflite", "prediction",
            "ai", "neural network", "tensorflow lite", "edge ai",
        ],
        use_case="inference",
    ),
    ArtifactMeta(
        artifact_id="serve-edge-chi",
        repo="github.com/teaching-on-testbeds/serve-edge-chi",
        title="Serving ML models on edge devices (Raspberry Pi 5)",
        machine_types=["raspberrypi5"],
        device_profiles=[],
        image="quay.io/jupyter/minimal-notebook:latest",
        architecture="arm64",
        gpu=False,
        tags=[
            "model serving", "quantization", "int8", "onnx", "onnxruntime",
            "benchmark", "latency", "throughput", "raspberry pi 5",
            "pytorch", "food classification", "jupyter",
        ],
        use_case="inference",
    ),
]


# --- chameleon corpus loader -------------------------------------------------

# The real KVM flavor set. `flavors_observed` is produced by a regex that also
# catches filenames and attribute lookups, so it reports "gpu.ipynb", "gpu.svg",
# "gpu.lower" and "m1.addressable_shards" alongside actual flavors. An
# allowlist is the only honest filter here: shape alone cannot tell "m1.tiny"
# from "m1.addressable_shards".
REAL_FLAVORS = frozenset({
    "m1.tiny", "m1.small", "m1.medium", "m1.large", "m1.xlarge", "m1.xxlarge",
    "g1.h100",
})


def _known_node_types() -> Set[str]:
    """Node type names the capability table vouches for.

    Read from the table, not from artifacts (R3): the table is the authority on
    which hardware exists, and using it as the filter means a bad extraction
    ("xavier", "raspberrypi-") cannot enter routing as if it were a real type.
    """
    path = settings.corpus_dir / "capability_table.yaml"
    if not path.is_file():
        return set()
    try:
        import yaml
        return set(yaml.safe_load(path.read_text(encoding="utf-8"))["node_types"])
    except Exception as exc:  # noqa: BLE001
        log.warning("capability table unreadable (%s); node types unfiltered", exc)
        return set()


def _primary_site(sites: List[str], api_family: str) -> str:
    """Which single site an artifact is filed under. `sites` keeps the rest."""
    if not sites:
        return ""
    if api_family == "kvm":
        for s in sites:
            if s.upper().startswith("KVM@"):
                return s
    elif api_family == "baremetal":
        for s in sites:
            if not s.upper().startswith("KVM@"):
                return s
    return sites[0]


def _load_corpus(corpus_dir: Optional[Path] = None) -> List[ArtifactMeta]:
    """Build ArtifactMeta records from the benchmark's artifact YAML.

    Returns [] when the corpus is not present. That is not an error: the
    advisor is installable on its own and stays edge-only without it. It IS
    logged, because an advisor that silently answers with 5 artifacts when you
    expected 95 is the harder failure to notice.
    """
    corpus_dir = Path(corpus_dir or settings.corpus_dir)
    adir = corpus_dir / "artifacts"
    if not adir.is_dir():
        log.info("no chameleon corpus at %s; registry stays edge-only", adir)
        return []

    import yaml

    known_types = _known_node_types()
    out: List[ArtifactMeta] = []
    for path in sorted(adir.glob("A*.yaml")):
        try:
            d = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("skipping unreadable artifact record %s: %s", path.name, exc)
            continue

        sites = list(d.get("site_observed") or [])
        family = d.get("api_family") or "none"
        if family in {"baremetal", "kvm"}:
            family_source = "observed"
        else:
            # "none" (25 records) and "mixed" (3) are not usable api_families.
            # The site is the better evidence, and saying so beats guessing.
            primary = _primary_site(sites, "")
            family = "kvm" if primary.upper().startswith("KVM@") else "baremetal"
            family_source = "derived_from_site"

        node_types = [t for t in (d.get("node_types_observed") or [])
                      if not known_types or t in known_types]
        flavors = [f for f in (d.get("flavors_observed") or [])
                   if f in REAL_FLAVORS]

        tags = list(d.get("retrieval_tags") or [])
        if tags:
            tags_source = "authored"
        else:
            # Weaker signal, and labelled as such. Deliberately NOT including
            # site names: every artifact at a site carries the same one, so it
            # separates nothing and only dilutes the tags that do.
            tags_source = "fallback"
            tags = list(d.get("workload_tags") or [])
            tags += list(d.get("resource_tags") or [])
            tags += node_types

        grounding = corpus_dir / (d.get("grounding") or f"grounding/{d['id']}.md")

        out.append(ArtifactMeta(
            artifact_id=d["id"],
            repo=d.get("repo_url") or "",
            title=d.get("trovi_title") or d.get("artifact_id") or d["id"],
            # machine_types is what the router unions into
            # candidate_machine_types to prune which sites get contacted, so
            # both reservable shapes belong in it.
            machine_types=node_types + flavors,
            device_profiles=[],
            image="",
            architecture="",
            gpu=bool(d.get("gpus_mentioned")),
            tags=[t for t in dict.fromkeys(tags) if t],
            site=_primary_site(sites, family),
            use_case="",
            sites=sites,
            node_types=node_types,
            flavors=flavors,
            api_family=family,
            workload_tags=list(d.get("workload_tags") or []),
            content_group=d.get("content_group") or "",
            grounding_file=grounding if grounding.is_file() else None,
            tags_source=tags_source,
            api_family_source=family_source,
            wing="chameleon",
        ))
    return out


CORPUS_ARTIFACTS: List[ArtifactMeta] = _load_corpus()

# Edge first, so registry order (which RouterTree preserves within a branch)
# puts the frozen entries exactly where they have always been.
ARTIFACTS: List[ArtifactMeta] = EDGE_ARTIFACTS + CORPUS_ARTIFACTS

ARTIFACTS_BY_ID = {a.artifact_id: a for a in ARTIFACTS}
