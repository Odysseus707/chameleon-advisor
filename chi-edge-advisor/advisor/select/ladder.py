"""The selection ladder: workload + live state -> one reservable node, or a refusal.

    rank candidates by capability and site
      -> free now?                      -> DONE
      -> free within 24h?               -> DONE, and say how long the wait is
      -> widen the candidate list, bounded, and try again
      -> INFEASIBLE

Deterministic and free of the LLM on purpose. Which hardware can run a job and
whether it is free are questions with answers; a model asked to do this
produces something that reads like an answer whether or not one exists.

WHERE THE CANDIDATES COME FROM, and why it is not what the design sketch said.

The sketch had the ladder derive candidate node types from the top-ranked
artifacts. Measured against the corpus, that cannot work: of the 29 bare-metal
types in the capability table, only 9 are named by any artifact at all. Gating
on artifact evidence would make 20 of 29 types - including every H100, every
A100, and the whole Zen3 and Icelake fleet - permanently unrecommendable, and
would fail the reservation suite by construction, since its golds rank types no
artifact mentions.

So the two sources answer the two questions they can actually answer:

    artifacts       WHICH SITE, and what configuration to run (image, grounding,
                    the prose in the recommendation). Retrieval's job.
    capability      WHICH HARDWARE is capable. The table's job, and only the
    table           table's - an artifact may say a type exists, it may never
                    say what that hardware can do (R3).
    live state      WHICH OF THOSE you can actually have right now.

Artifact coverage still shows up in the output, as provenance: a recommendation
grounded in an artifact is a different claim from one resting on the capability
table alone, and the caller is told which it got.

THE THREE RULES THAT MAKE REFUSALS HONEST:

  R4  A null measurement is not a measurement of absence. Blazar reported no
      RAM for 17 of the 29 types; `ram_gb: None` FAILS a min_ram_gb, never
      satisfies it.
  R5  Unknown availability is not availability. `free_now is None` means the
      backend does not know, and a node we cannot see is not a node we can have.
  R6  Site is part of correctness. gpu_rtx_6000 is CHI@UC only; gpu_mi100 and
      gpu_p100 are CHI@TACC only. Recommending hardware that is not at the
      chosen site is wrong in a way no amount of waiting fixes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence

from ..availability.base import DeviceAvailability
from ..inventory.catalog import DeviceType, capability_ranking_weights

log = logging.getLogger(__name__)

# How far ahead a lease is worth waiting for before the answer becomes "no".
FUTURE_HORIZON_HOURS = 24.0
# Candidates considered on the first pass, and how far the list may widen.
INITIAL_CANDIDATES = 3
EXPANSION_STEP = 2
MAX_EXPANSIONS = 2


@dataclass
class Request:
    """What the user asked for, separated from how they phrased it."""

    site: Optional[str] = None
    count: int = 1
    hours: int = 3
    # Same shape as the benchmark's item["requires"]. These ELIMINATE: they
    # are either the user's own words or a class requirement, and a node
    # failing one cannot run the job.
    requires: Dict = field(default_factory=dict)
    # Magnitudes we inferred rather than were told. These only RANK. Refusing
    # on the strength of our own guess fabricates an infeasibility, and a user
    # can see that a tight node is tight but cannot see a refusal that never
    # reached them.
    soft_requires: Dict = field(default_factory=dict)
    # Stated in the answer, always: the reader is entitled to know which
    # constraints came from them and which came from us.
    assumptions: List[str] = field(default_factory=list)
    api_family: str = "baremetal"
    # What "now" means when reading a next-free timestamp. None is the wall
    # clock, which is right for a live probe and wrong for a pinned snapshot:
    # the bare-metal snapshots are recorded at a fixed instant, so against the
    # wall clock every wait shrinks by a day each day and the 24h horizon that
    # separates the `future` rung from `infeasible_busy` is crossed by the
    # calendar rather than by the data. A snapshot-backed caller passes its
    # own `_meta.recorded` and the answer stops moving.
    now: Optional[datetime] = None


@dataclass
class Candidate:
    """One node type, and everything we concluded about it."""

    machine_type: str
    site: str
    free: int = 0
    total: int = 0
    unknown: int = 0          # hosts whose state the backend could not report
    capable: bool = True
    reject_reason: str = ""   # why it cannot serve, "" when it can
    # Why it CAN serve, "" when it cannot. Not the inverse of the above:
    # both are empty for a type nothing was asked of.
    accept_reason: str = ""
    capability_score: int = 0
    next_free_hours: Optional[float] = None
    covered_by: List[str] = field(default_factory=list)
    example_host: Optional[str] = None   # a specific host verified free
    # Does it also clear the inferred (guessed) magnitudes? None when nothing
    # was inferred. False is not a rejection - it orders lower and says why.
    meets_soft: Optional[bool] = None
    soft_gap: str = ""
    # Did the backend report on this type AT ALL? Distinct from free==0.
    # `total` falls back to the capability table's static node_count when the
    # backend said nothing, so total is never 0 for a known type and cannot
    # answer this. Conflating the two is how "we could not reach the site"
    # gets reported as "every node there is taken".
    state_known: bool = False

    @property
    def grounded(self) -> bool:
        return bool(self.covered_by)


@dataclass
class Rung:
    """Which rung of the ladder produced the answer, and what it cost."""

    name: str            # free_now | future | infeasible_capability |
                         # infeasible_busy | unknown_availability |
                         # no_host_state
    expansions: int = 0
    wait_hours: Optional[float] = None
    considered: int = 0
    detail: str = ""

    @property
    def satisfied(self) -> bool:
        return self.name in {"free_now", "future", "no_host_state"}


@dataclass
class LadderResult:
    rung: Rung
    chosen: Optional[Candidate]
    ranked: List[Candidate] = field(default_factory=list)   # feasible, best first
    rejected: List[Candidate] = field(default_factory=list)  # with reasons
    site: Optional[str] = None
    # Does ANY hardware on the testbed that satisfies this requirement have an
    # artifact documenting it? Computed across every site, ignoring the site
    # filter, because "nobody has ever written this up" is a fact about the
    # corpus and not about where you happen to be asking from. Empty means no
    # such hardware exists at all.
    requirement_types: List[str] = field(default_factory=list)
    requirement_grounded: bool = False


# --- capability ---------------------------------------------------------------

def meets(spec: DeviceType, req: Dict) -> Optional[str]:
    """None if the type satisfies every requirement, else why not.

    Ported deliberately from the benchmark's own solver
    (corpus_v2/tools/build_reservation_items.py) rather than re-derived, so the
    advisor and the thing grading it disagree about hardware for real reasons
    and never because two people wrote the same rule twice.

    A null measurement FAILS a minimum. Blazar not reporting a host's RAM is
    not evidence that the host has enough (R4).
    """
    if "accelerator" in req:
        want = req["accelerator"]
        want = [want] if isinstance(want, str) else list(want)
        if spec.accelerator not in want:
            return f"accelerator is {spec.accelerator}, needs {'/'.join(want)}"
    if "min_cuda_compute" in req:
        cc = spec.cuda_compute
        if cc is None or float(cc) < float(req["min_cuda_compute"]):
            return f"cuda_compute {cc or 'none'} < {req['min_cuda_compute']}"
    if "min_tensor_cores" in req and (spec.tensor_cores or 0) < req["min_tensor_cores"]:
        return "no tensor cores"
    if "min_ram_gb" in req and (spec.ram_gb or 0) < req["min_ram_gb"]:
        return f"{spec.ram_gb or 'unknown'} GB < {req['min_ram_gb']} GB"
    if "min_vcpus" in req and (spec.vcpus or 0) < req["min_vcpus"]:
        return f"{spec.vcpus or 'unknown'} vcpus < {req['min_vcpus']}"
    if "min_vram_gb" in req and (spec.vram_gb_per_gpu or 0) < req["min_vram_gb"]:
        # Per-GPU, not summed across the node: a model that will not fit in one
        # card's memory does not fit because the node has four of them.
        return (f"{spec.vram_gb_per_gpu or 'unknown'} GB VRAM per GPU < "
                f"{req['min_vram_gb']} GB")
    return None


def why_it_qualifies(spec: DeviceType, req: Dict) -> str:
    """The affirmative mirror of meets(): why this type CAN serve.

    meets() explains every rejection and nothing explained an acceptance, so
    the ranked list arrived as bare free counts and the reader had to work out
    for themselves why those counts were an answer.

    RB18 is what that cost. A single-node CPU batch job, on a snapshot where
    every CPU type was reserved: the ladder ranked three free GPU types, which
    is correct, because no accelerator was required and a GPU node's CPUs run a
    CPU job perfectly well. The model was handed that list and replied "there
    are no CPU nodes available ... it's not possible to reserve a node". It was
    not missing the hardware. It was missing the sentence.

    The incidental-accelerator clause is therefore the point of this function,
    not a flourish: it is the one fact that made that list usable.
    """
    # "none" is a VALUE in this field, not an absence: 16 of the 29 bare-metal
    # types carry the literal string. Testing truthiness produced "its none is
    # incidental" on every CPU type.
    accel = spec.accelerator if spec.accelerator not in (None, "", "none") else None

    bits = []
    if "accelerator" not in req and accel:
        have = []
        if spec.vcpus:
            have.append(f"{spec.vcpus} vCPUs")
        if spec.ram_gb:
            have.append(f"{spec.ram_gb} GB")
        detail = f" ({', '.join(have)})" if have else ""
        bits.append(f"no accelerator was required, so its {accel} "
                    f"is incidental - the node's CPUs{detail} serve the job")
    if "accelerator" in req and accel:
        bits.append(f"{accel} accelerator")
    if "min_cuda_compute" in req:
        bits.append(f"CUDA compute {spec.cuda_compute}")
    if "min_tensor_cores" in req and spec.tensor_cores:
        bits.append(f"{spec.tensor_cores} tensor cores")
    if "min_ram_gb" in req:
        bits.append(f"{spec.ram_gb} GB RAM against the {req['min_ram_gb']} GB asked for")
    if "min_vcpus" in req:
        bits.append(f"{spec.vcpus} vCPUs against the {req['min_vcpus']} asked for")
    if "min_vram_gb" in req:
        bits.append(f"{spec.vram_gb_per_gpu} GB VRAM per GPU")
    if not bits:
        # Nothing was required and there is no accelerator to explain away.
        bits.append("no hardware requirement was stated, so every type at this "
                    "site qualifies and this one is ranked on availability")
    return "; ".join(bits)


def capability_score(spec: DeviceType, weights: Optional[Dict] = None) -> int:
    w = weights or capability_ranking_weights()
    return (int(spec.cuda_cores or 0) * w.get("cuda_cores", 0)
            + int(spec.tensor_cores or 0) * w.get("tensor_cores", 0)
            + int(spec.ram_gb or 0) * w.get("ram_gb", 0)
            + int(spec.vcpus or 0) * w.get("vcpus", 0))


# --- live state ---------------------------------------------------------------

def _hours_until(stamp: Optional[str], now: Optional[datetime] = None
                 ) -> Optional[float]:
    """Hours from now until an ISO8601 instant, or None if unparseable.

    None is returned rather than 0.0 on a parse failure, because 0.0 would read
    as "free immediately" - turning a timestamp we could not understand into
    the most optimistic possible claim.
    """
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        log.warning("cannot parse availability timestamp %r", stamp)
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = (when - (now or datetime.now(timezone.utc))).total_seconds() / 3600.0
    if delta <= 0:
        # In the past. On a host that reports free_now=False this is not
        # evidence the host is free - it is a window that has closed, or a
        # snapshot older than the question. Clamping it to 0.0 turns "we do
        # not know when this frees" into "it is free right now", which is the
        # single most optimistic reading of data that says the opposite.
        return None
    return delta


def _tally(availability: Iterable[DeviceAvailability], site: Optional[str],
           now: Optional[datetime] = None) -> Dict[str, Dict]:
    """Per node type: how many are free, unknown, and total, at this site.

    Three counters, not two. A host the backend could not report on is neither
    free nor busy, and folding it into either one is a claim we cannot support
    (R5). `reservable is False` is a third thing again - maintenance or
    disabled - and offering it produces a spec that cannot be submitted.
    """
    out: Dict[str, Dict] = {}
    for dev in availability:
        if site and dev.site and dev.site != site:
            continue
        row = out.setdefault(dev.machine_type,
                             {"free": 0, "unknown": 0, "total": 0,
                              "waits": [], "host": None, "host_name": None})
        row["total"] += 1
        if dev.reservable is False:
            continue                     # cannot be booked at all
        if dev.free_now is None:
            row["unknown"] += 1          # R5: unknown is not free
            continue
        if dev.free_now:
            row["free"] += 1
            if row["host"] is None:
                row["host"] = dev.device_uid or None
                row["host_name"] = dev.device_name
        else:
            hrs = _hours_until(dev.next_free_window or dev.reserved_until, now)
            if hrs is not None:
                row["waits"].append(hrs)
    for row in out.values():
        row["waits"].sort()
    return out


def _wait_for(row: Dict, count: int) -> Optional[float]:
    """How long until `count` hosts of this type are free, or None.

    A LOWER BOUND, and deliberately labelled as one. Blazar gives a per-host
    next-free instant; it does not say the host stays free afterwards, so the
    count-th soonest wait is when the count-th host *becomes* available, not a
    guarantee that all of them overlap. It is the right shape for "come back
    in about four hours" and the wrong shape for a promise.
    """
    still_needed = count - row["free"]
    if still_needed <= 0:
        return 0.0
    if len(row["waits"]) < still_needed:
        return None            # not enough hosts will free up at all
    return row["waits"][still_needed - 1]


# --- the ladder ---------------------------------------------------------------

def _build(catalog: Sequence[DeviceType], availability, request) -> List[Candidate]:
    """Every type at the site, scored, filtered, and told why."""
    weights = capability_ranking_weights()
    counts = _tally(availability, request.site, request.now)
    out: List[Candidate] = []
    for spec in catalog:
        # R6: site membership first. A type that is not here cannot be had
        # here, and no amount of waiting changes that.
        if request.site and request.site not in (spec.sites or []):
            continue
        if request.api_family and spec.api_family != request.api_family:
            continue
        row = counts.get(spec.machine_type,
                         {"free": 0, "unknown": 0, "total": 0,
                          "waits": [], "host": None, "host_name": None})
        why = meets(spec, request.requires)
        soft_why = (meets(spec, request.soft_requires)
                    if request.soft_requires else None)
        out.append(Candidate(
            machine_type=spec.machine_type,
            site=request.site or (spec.sites[0] if spec.sites else ""),
            free=row["free"],
            total=row["total"] or spec.node_count,
            unknown=row["unknown"],
            capable=why is None,
            reject_reason=why or "",
            accept_reason=("" if why else
                           why_it_qualifies(spec, request.requires)),
            capability_score=capability_score(spec, weights),
            # Time until ENOUGH hosts are free, not until one is. A type with
            # two free hosts does not answer a three-node request sooner
            # because one of its two is available now.
            next_free_hours=_wait_for(row, request.count),
            state_known=row["total"] > 0,
            meets_soft=None if not request.soft_requires else soft_why is None,
            soft_gap=soft_why or "",
            covered_by=list(spec.covered_by),
            example_host=row.get("host_name") or row.get("host"),
        ))
    # The testbed's own ranking rule, read from the capability table: free
    # count first, then capability, then name for a stable tie.
    #
    # Inferred magnitudes enter HERE and nowhere else. A candidate that misses
    # a guessed bar sorts below one that clears it and is never removed, so a
    # guess can cost a node its rank but never costs the user the option. With
    # nothing inferred, meets_soft is None everywhere and the first key is
    # constant, leaving the ordering byte-identical to the rule the golds were
    # solved with - which is what keeps rank-1 reproducible.
    out.sort(key=lambda c: (c.meets_soft is False,
                            -c.free, -c.capability_score, c.machine_type))
    return out


def _requirement_grounding(catalog, request):
    """Which hardware anywhere meets this need, and is any of it documented?

    Site-blind on purpose. Whether an artifact exists is a property of the
    corpus, not of the site in the question, and the answer "no artifact
    documents FPGA work anywhere on this testbed" is worth saying to someone
    asking about FPGAs at a site that has none.
    """
    types = [d for d in catalog if meets(d, request.requires) is None]
    return ([d.machine_type for d in types],
            any(d.covered_by for d in types))


def select(catalog: Sequence[DeviceType],
           availability: Sequence[DeviceAvailability],
           request: Request) -> LadderResult:
    """Walk the ladder. Returns the rung it stopped on, always."""
    req_types, req_grounded = _requirement_grounding(catalog, request)
    everything = _build(catalog, availability, request)
    feasible = [c for c in everything if c.capable]
    rejected = [c for c in everything if not c.capable]

    if not feasible:
        # Nothing here can do the job. This is a claim about the hardware, and
        # it does not improve by waiting.
        return LadderResult(
            rung=Rung(name="infeasible_capability", considered=len(everything),
                      detail=("no node type at %s satisfies the requirement"
                              % (request.site or "this site"))),
            chosen=None, ranked=[], rejected=rejected, site=request.site,
            requirement_types=req_types, requirement_grounded=req_grounded)

    # KVM reserves flavors, not hosts. Blazar's per-host view of KVM@TACC
    # reports hypervisor classes (compute, QEMU, gpu), not reservable types, so
    # a free-host count there answers no question anyone can ask of it. Saying
    # so beats inventing an availability verdict.
    if request.api_family == "kvm":
        return LadderResult(
            rung=Rung(name="no_host_state", considered=len(everything),
                      detail="KVM reserves flavors, not hosts; no per-host "
                             "availability applies"),
            chosen=feasible[0], ranked=feasible, rejected=rejected,
            site=request.site, requirement_types=req_types,
            requirement_grounded=req_grounded)

    # "We could not look" is not "everything is taken". If no candidate has a
    # single availability row, we have no state at all - and reporting that as
    # busy is a confident claim about a site we never reached. This is the
    # live CHI@UC case today: the application credential is scoped to
    # CHI-231225 at CHI@TACC, so CHI@UC returns nothing, and an advisor that
    # calls that "busy" is inventing the part that mattered.
    if not any(c.state_known for c in feasible):
        return LadderResult(
            rung=Rung(name="unknown_availability", considered=len(feasible),
                      detail=("no availability data for %s; %d node types "
                              "there are capable, but whether any is free is "
                              "unknown, not no."
                              % (request.site or "this site", len(feasible)))),
            chosen=None, ranked=feasible, rejected=rejected, site=request.site,
            requirement_types=req_types, requirement_grounded=req_grounded)

    limit = INITIAL_CANDIDATES
    for expansions in range(MAX_EXPANSIONS + 1):
        window = feasible[:limit]

        for cand in window:
            if cand.free >= request.count:
                return LadderResult(
                    rung=Rung(name="free_now", expansions=expansions,
                              considered=len(window)),
                    chosen=cand, ranked=feasible, rejected=rejected,
                    site=request.site, requirement_types=req_types,
                    requirement_grounded=req_grounded)

        # Nothing free now. Would anything free up soon enough to be useful?
        # next_free_hours already accounts for request.count (see _wait_for),
        # so a type that can never assemble enough hosts is absent from this
        # list rather than offered with an optimistic wait.
        waits = [c for c in window
                 if c.next_free_hours is not None
                 and 0.0 < c.next_free_hours <= FUTURE_HORIZON_HOURS]
        if waits:
            best = min(waits, key=lambda c: c.next_free_hours)
            return LadderResult(
                rung=Rung(name="future", expansions=expansions,
                          wait_hours=best.next_free_hours,
                          considered=len(window),
                          detail="free in %.1fh" % best.next_free_hours),
                chosen=best, ranked=feasible, rejected=rejected,
                site=request.site, requirement_types=req_types,
                requirement_grounded=req_grounded)

        if limit >= len(feasible):
            break                      # widening cannot add anything
        limit += EXPANSION_STEP

    # Everything capable is busy. Different claim from "nothing can do this",
    # and it must not share a headline with it: the hardware exists and fits,
    # it is simply taken.
    capped = limit >= len(feasible)
    return LadderResult(
        rung=Rung(name="infeasible_busy", expansions=MAX_EXPANSIONS,
                  considered=min(limit, len(feasible)),
                  detail=("all %d capable types are busy%s" % (
                      len(feasible),
                      "" if capped else
                      "; stopped after %d expansions without exhausting the list"
                      % MAX_EXPANSIONS))),
        chosen=None, ranked=feasible, rejected=rejected, site=request.site,
        requirement_types=req_types, requirement_grounded=req_grounded)


# --- rendering ----------------------------------------------------------------

def to_recommendation(result: LadderResult, request: Request, *,
                      image: str = "", grounded_by: Optional[List[str]] = None,
                      top_n: int = 3) -> "Recommendation":
    """Turn a ladder verdict into the schema the validator and emitter speak.

    A refusal is a Recommendation too, with an empty machine_type. The two
    refusals must not share a headline: "nothing here can do this" is a claim
    about the hardware, and stating it when the hardware fits and is merely
    reserved is simply false. Only the busy refusal carries `alternatives`,
    because only there is there something to come back for.
    """
    from ..reason.schema import Recommendation

    ranked = result.ranked[:top_n]
    chosen = result.chosen
    alternatives = [c.machine_type for c in ranked
                    if not chosen or c.machine_type != chosen.machine_type]

    if chosen is None:
        if result.rung.name == "unknown_availability":
            reasoning = (
                "Cannot say. %s Capable node types there: %s. Re-run with "
                "credentials for that site, or declare a site the advisor can "
                "reach." % (result.rung.detail,
                            ", ".join(c.machine_type for c in result.ranked[:6])))
        elif result.rung.name == "infeasible_busy":
            reasoning = (
                "Every node type at %s that meets this requirement is "
                "currently reserved: %s. This is an availability limit, not a "
                "capability one - the hardware exists and fits, it is taken. "
                "%s" % (result.site or "this site",
                        ", ".join(c.machine_type for c in result.ranked),
                        result.rung.detail))
        else:
            reasoning = (
                "No node type at %s can satisfy this request. %s Rejected: %s"
                % (result.site or "this site", result.rung.detail,
                   "; ".join(f"{c.machine_type} ({c.reject_reason})"
                             for c in result.rejected[:6]) or "none"))
        return Recommendation(
            machine_type="", count=request.count,
            duration_hours=request.hours, architecture="", image="",
            reasoning=reasoning, site=result.site, api_family=request.api_family,
            alternatives=(alternatives if result.rung.name
                          in {"infeasible_busy", "unknown_availability"} else []),
            selection_rung=result.rung.name,
            assumptions=list(request.assumptions),
            grounded_by=list(grounded_by or []), produced_by="ladder")

    bits = [f"{chosen.machine_type}: {chosen.free} of {chosen.total} free at "
            f"{result.site}"]
    if request.assumptions:
        bits.append("assumed: " + "; ".join(request.assumptions))
    if chosen.meets_soft is False:
        # The pick did not clear a bar WE invented. Say so plainly rather than
        # either hiding it or refusing: the hardware is real and available,
        # and the assumption is the shaky part.
        bits.append(f"note: this does not meet an assumed requirement "
                    f"({chosen.soft_gap}); that requirement was inferred from "
                    "the request, not stated in it, so it has not been used to "
                    "rule anything out")
    if result.rung.name == "future":
        bits.append("nothing is free right now; the earliest is in "
                    f"{result.rung.wait_hours:.1f}h")
    if result.rung.name == "no_host_state":
        bits.append(result.rung.detail)
    if chosen.unknown:
        # Said out loud rather than folded into the free count: hosts the
        # backend could not report on are not hosts we can promise.
        bits.append(f"{chosen.unknown} host(s) of this type have unknown state "
                    "and were not counted as free")
    if not chosen.grounded:
        bits.append("no artifact in the corpus covers this node type; the "
                    "recommendation rests on the capability table alone")
    if result.rejected:
        bits.append("rejected: " + "; ".join(
            f"{c.machine_type} ({c.reject_reason})" for c in result.rejected[:4]))

    return Recommendation(
        machine_type=chosen.machine_type,
        count=request.count,
        duration_hours=request.hours,
        architecture="",
        image=image,
        reasoning=". ".join(bits) + ".",
        device_name=chosen.example_host if result.rung.name == "free_now" else None,
        gpu=bool(chosen.capability_score) and chosen.machine_type.startswith("gpu"),
        site=result.site,
        api_family=request.api_family,
        alternatives=alternatives,
        selection_rung=result.rung.name,
        assumptions=list(request.assumptions),
        wait_hours=result.rung.wait_hours,
        grounded_by=list(grounded_by or []),
        produced_by="ladder",
    )
