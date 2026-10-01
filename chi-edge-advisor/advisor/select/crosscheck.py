"""Do the artifacts agree with how we read this use case?

The idea is sound and worth having: if somebody already published a Trovi
artifact doing this same job on a Skylake node, and we have just inferred that
it needs an H100, the likelier explanation is that we misread the use case -
not that every previous author under-provisioned.

BUT THE OBVIOUS VERSION OF THIS CHECK IS BACKWARDS, and measurably so.

The five most capable node types on the testbed - gpu_h100, gpu_a100_nvlink,
gpu_v100, gpu_a100_pcie, gpu_p100_nvlink - are named by ZERO artifacts. 18 of
the 29 types are named by none. A check that reads "no artifact mentions the
hardware we chose" as disagreement would therefore fire on every single
high-end GPU recommendation and be wrong every time, because artifact silence
here tracks two things that have nothing to do with correctness:

  the corpus is thin      22 of 90 artifacts carry authored retrieval_tags
  the corpus is old       pinned to August 2026 clones, so it cannot mention
                          hardware installed since, and P6 records the
                          testbed moving underneath it - compute_haswell had
                          27 hosts in the capture and was gone from live
                          Blazar nine hours later

So the check fires ONLY on evidence: an artifact that does a comparable job
AND names hardware the capability table knows. Absence of evidence is not
recorded as evidence of anything.

It emits a NOTE, never a veto. Two ways it can be wrong even when it fires -
the artifact's author may have used what was free rather than what was needed,
and the job in the prompt may be a bigger instance of the same shape - and
neither is detectable from here. The reader gets the observation and makes the
call.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..artifacts.registry import ARTIFACTS, ArtifactMeta
from ..inventory.catalog import DeviceType
from ..inventory.tiers import Tier, tier_for

_TOKEN = re.compile(r"[a-z0-9]+")

#: How much tag overlap makes an artifact's workload "comparable". Two distinct
#: matching tokens, or one whole multi-word tag. One bare token is far too
#: cheap - "model" or "data" would make most of the corpus comparable to most
#: of the corpus, and a check that always fires says nothing.
MIN_TAG_HITS = 2


def _tokens(text: str) -> set:
    return set(_TOKEN.findall((text or "").lower()))


@dataclass
class CrossCheck:
    """What the corpus has to say, and how much of it there was to hear."""

    fired: bool = False
    kind: str = ""              # "" | class_disagreement | tier_disagreement
    note: str = ""
    comparable: List[str] = field(default_factory=list)   # artifact ids
    their_types: List[str] = field(default_factory=list)
    our_type: str = ""

    @property
    def had_evidence(self) -> bool:
        """Was there any comparable artifact at all?

        Distinct from `fired`. No evidence means the corpus was silent, which
        is not agreement and must never be reported as endorsement.
        """
        return bool(self.comparable)


def _comparable_artifacts(workload: str, known_types: set,
                          artifacts: Sequence[ArtifactMeta]) -> List[ArtifactMeta]:
    """Artifacts doing a similar job AND naming hardware we can place."""
    want = _tokens(workload)
    out = []
    for meta in artifacts:
        if meta.wing == "edge":
            continue                      # different testbed, different rules
        if not any(t in known_types for t in meta.node_types):
            continue                      # names no placeable hardware
        hits = 0
        for tag in list(meta.tags) + list(meta.workload_tags):
            ttoks = _tokens(tag)
            if not ttoks:
                continue
            if ttoks <= want and len(ttoks) > 1:
                hits += MIN_TAG_HITS       # a whole multi-word tag present
            elif ttoks & want:
                hits += len(ttoks & want)
        if hits >= MIN_TAG_HITS:
            out.append(meta)
    return out


def crosscheck(workload: str, our_type: str,
               catalog: Sequence[DeviceType],
               artifacts: Optional[Sequence[ArtifactMeta]] = None) -> CrossCheck:
    """Compare our pick against what comparable artifacts actually used."""
    by_name: Dict[str, DeviceType] = {d.machine_type: d for d in catalog}
    spec = by_name.get(our_type)
    if spec is None:
        return CrossCheck(our_type=our_type)

    ours = tier_for(spec)
    comparable = _comparable_artifacts(workload, set(by_name),
                                       artifacts if artifacts is not None
                                       else ARTIFACTS)
    if not comparable:
        # Silence. Not agreement, not disagreement - nothing was heard.
        return CrossCheck(our_type=our_type)

    # Every type the comparable artifacts named, OURS INCLUDED. Dropping our
    # own type here was a real bug: an artifact that used exactly the hardware
    # we are recommending then looked like it had used something else, and the
    # strongest possible agreement was reported as disagreement.
    named: Dict[str, Tier] = {}
    for meta in comparable:
        for t in meta.node_types:
            if t in by_name:
                named[t] = tier_for(by_name[t])
    theirs = {k: v for k, v in named.items() if k != our_type}
    result = CrossCheck(
        our_type=our_type,
        comparable=[m.artifact_id for m in comparable],
        their_types=sorted(theirs),
    )
    if not theirs:
        return result

    # Class disagreement: they did this job on a different KIND of machine.
    # Reported as an observation, not a ranking - "they used a CPU" is a fact,
    # "a CPU is worse" is not something this module is entitled to say.
    # Only when NOT ONE comparable artifact used our class. If any of them
    # reached for the same kind of machine, the corpus agrees with the reading
    # and the others are simply a different part of the same workflow - a
    # notebook artifact that names both a GPU node and a CPU node is not
    # evidence against choosing the GPU.
    agrees = any(t.accel_class == ours.accel_class for t in named.values())
    other_class = {name: t for name, t in theirs.items()
                   if t.accel_class != ours.accel_class}
    if other_class and not agrees and ours.accel_class != "none":
        names = ", ".join(sorted(other_class))
        classes = sorted({t.accel_class for t in other_class.values()})
        result.fired = True
        result.kind = "class_disagreement"
        result.note = (
            f"{len(comparable)} artifact(s) in the corpus doing comparable work "
            f"ran on {names} ({'/'.join(classes)}-class), while this "
            f"recommends {our_type} ({ours.accel_class}-class). Worth "
            f"confirming the accelerator is really needed - though the corpus "
            f"is pinned to August 2026 and its authors may have used whatever "
            f"was free at the time.")
        return result

    # Tier disagreement, within one class: they reached materially lower.
    # Measured over `named`, which includes our own type, for the same reason
    # the class check is: an artifact that used exactly what we recommend is
    # the strongest agreement available and must break the claim that EVERY
    # comparable artifact reached lower. It is comparable to itself and it is
    # not lower, so the two counts diverge and the note does not fire.
    same_class = {n: t for n, t in named.items() if t.comparable_to(ours)}
    lower = {n: t for n, t in same_class.items() if ours.exceeds(t) is True}
    if lower and len(lower) == len(same_class):
        names = ", ".join(sorted(lower))
        result.fired = True
        result.kind = "tier_disagreement"
        result.note = (
            f"Every comparable artifact in the corpus ({len(comparable)}) used "
            f"lower-tier hardware for this kind of work: {names}, against "
            f"{our_type}. That may mean the requirement was read too high; it "
            f"may equally mean the corpus predates {our_type}.")
    return result
