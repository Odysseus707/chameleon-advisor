"""What does this job actually need? Turning a use case into specs.

The advisor could always CHECK a requirement; it was never able to WORK ONE
OUT. The benchmark hands it `requires` from the item and the CLI passed `{}`,
so for a real user asking "I want to fine-tune a vision model" the capability
filter did not bind at all - no accelerator constraint, no memory floor,
nothing. This module is the missing step.

TWO PATHS, AND WHY THE SECOND IS OFF BY DEFAULT.

  extract()   Explicit statements only - "180 GB or more", "with CUDA and
              tensor cores", "3-node MPI job". Pure, no network, always runs.
              This alone makes the filter bind, and it is all the benchmark's
              own prompts need, because they state their requirements outright.

  LLM         Implicit use cases - "fine-tune a 7B model" implies an
              accelerator and a memory floor that no regex can find. Opt-in via
              ADVISOR_LLM_SPECS, default OFF, exactly as ADVISOR_LLM_ROUTER is
              for intent routing. A collected benchmark run must produce the
              same answer next year, and a model in the loop by default breaks
              that.

WHAT AN INFERENCE IS ALLOWED TO DO, WHICH IS THE WHOLE DESIGN.

An inferred requirement is our guess about the user's job, not a fact about
their job, and the two must not have the same power:

  CLASS requirements eliminate, even when inferred. Getting CUDA-vs-ROCm wrong
  does not make the job slow, it makes it not run - a CUDA binary will not
  execute on an MI100 at any size. A wrong class is a wrong answer either way,
  so there is nothing to be gained by hedging.

  MAGNITUDE requirements only RANK when inferred. If we guess a job needs 80 GB
  of VRAM and nothing on the site has 80 GB, the honest answer is "assuming it
  needs 80 GB, nothing qualifies - here is what is actually available" and NOT
  a refusal. Refusing on the strength of our own guess is fabricating an
  infeasibility, which is a worse failure than recommending a node that turns
  out to be tight: the user can see a tight node is tight, and cannot see a
  refusal that never happened.

  Explicit user numbers eliminate, exactly as they do today. "180 GB or more"
  is the user telling us, not us guessing.

ERRING UPWARD. An uncertain requirement rounds UP, and it rounds up to a value
the fleet actually has (see FLEET_TIERS) rather than to a round number, so the
requirement always lands on real hardware. Slightly overpowered costs queue
time; underpowered costs the whole run.

R4 is untouched throughout: a null measurement fails a minimum, guessed or not.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

#: Keys that describe WHAT KIND of machine, not how much of it. These
#: eliminate even when inferred - see the module docstring.
CLASS_KEYS = frozenset({"accelerator"})

#: Rungs the fleet actually offers, so a rounded-up requirement lands on real
#: hardware instead of a tidy number nobody built. cuda_compute is the exact
#: set present in the capability table; the memory ladders are standard part
#: sizes. Rounding to 96 GB of VRAM would be arithmetically neat and would
#: describe no card on the testbed.
FLEET_TIERS: Dict[str, List[float]] = {
    "min_cuda_compute": [3.7, 5.2, 6.0, 7.0, 7.5, 8.0, 9.0],
    "min_vram_gb": [12, 16, 24, 32, 40, 48, 80],
    "min_ram_gb": [64, 125, 128, 188, 256, 384, 512],
    "min_vcpus": [8, 16, 24, 28, 32, 48, 64, 96, 128],
}

# Order is load-bearing. "a ROCm/HIP port of an existing CUDA kernel" names
# both, and the one the user is porting TO is the one they need; the CUDA
# mention is the thing being left behind. Same for an FPGA workflow that
# mentions a CUDA baseline. The more specific, less common accelerator wins.
_ACCELERATORS = (
    (r"\brocm\b|\bhip\b|\bmi\d{2,3}\b", "rocm"),
    (r"\bfpga\b|\bbitstream\b|\bverilog\b|\bvhdl\b", "fpga"),
    (r"\boneapi\b|\blevel zero\b|\bponte vecchio\b|\bsycl\b", "oneapi"),
    (r"\bcuda\b|\bnvidia\b|\btensorrt\b|\bcudnn\b", "cuda"),
)

# A bare "256 GB" could be disk, RAM or VRAM. Each pattern below requires the
# unit to sit next to a word that says WHICH, because guessing wrong here
# silently applies a memory floor to the wrong resource.
_VRAM = re.compile(
    r"(\d+)\s*(?:gb|gib|g)\b[^.]{0,24}?\b(?:vram|gpu memory|video memory)"
    r"|\b(?:vram|gpu memory|video memory)\b[^.]{0,24}?(\d+)\s*(?:gb|gib|g)\b",
    re.I)
_RAM = re.compile(
    r"(\d+)\s*(?:gb|gib|g)\b[^.]{0,24}?\b(?:ram|memory|in-memory)"
    r"|\b(?:ram|memory|in-memory)\b[^.]{0,40}?(\d+)\s*(?:gb|gib|g)\b",
    re.I)
_VCPUS = re.compile(r"(\d+)\s*(?:vcpus?|cores?|threads?)\b", re.I)
_COMPUTE_CAP = re.compile(
    r"compute\s+(?:capability|cap)\s*(?:of\s*)?(\d+(?:\.\d+)?)", re.I)
_TENSOR = re.compile(r"\btensor\s+cores?\b", re.I)
_NODES = re.compile(r"\b(\d+)[\s-]*nodes?\b", re.I)


@dataclass
class InferredRequirement:
    """A requirement, plus where every part of it came from.

    `origin` is not bookkeeping - it decides whether a key eliminates hardware
    or merely orders it, and it is what lets the answer say "assuming X" rather
    than asserting X.
    """

    requires: Dict = field(default_factory=dict)
    origin: Dict[str, str] = field(default_factory=dict)   # explicit|inferred|rounded_up
    assumptions: List[str] = field(default_factory=list)
    count: Optional[int] = None
    rounded_up: bool = False

    def hard(self) -> Dict:
        """What may eliminate a node: everything explicit, plus the class."""
        return {k: v for k, v in self.requires.items()
                if self.origin.get(k) == "explicit" or k in CLASS_KEYS}

    def soft(self) -> Dict:
        """What may only rank: magnitudes we guessed at.

        Everything not hard, so a new origin - `recalled` was added after
        `inferred` and `rounded_up` - is soft by default. A guess has to be
        deliberately promoted, never accidentally.
        """
        hard = self.hard()
        return {k: v for k, v in self.requires.items() if k not in hard}

    def _set(self, key, value, origin, note=""):
        self.requires[key] = value
        self.origin[key] = origin
        if note:
            self.assumptions.append(note)
        if origin == "rounded_up":
            self.rounded_up = True

    def describe(self) -> str:
        if not self.requires:
            return "no hardware requirement could be determined from the request"
        parts = [f"{k}={v} ({self.origin.get(k, 'explicit')})"
                 for k, v in sorted(self.requires.items())]
        return "; ".join(parts)


def round_up_to_fleet(key: str, value: float) -> float:
    """Raise a guess to the next rung the fleet actually offers.

    Returns the value unchanged when it already exceeds every rung - a
    requirement larger than anything on the testbed is a real answer ("nothing
    here is big enough"), and quietly capping it to the biggest node would
    convert that into a false recommendation.
    """
    rungs = FLEET_TIERS.get(key)
    if not rungs:
        return value
    for r in rungs:
        if r >= value:
            return r
    return value


def extract(workload: str) -> InferredRequirement:
    """Requirements the user stated outright. Deterministic, no network."""
    out = InferredRequirement()
    text = workload or ""

    for pattern, name in _ACCELERATORS:
        if re.search(pattern, text, re.I):
            out._set("accelerator", name, "explicit")
            break

    if _TENSOR.search(text):
        out._set("min_tensor_cores", 1, "explicit")
        # Tensor cores are a CUDA feature; naming them names the class.
        if "accelerator" not in out.requires:
            out._set("accelerator", "cuda", "explicit",
                     "tensor cores were requested, which implies CUDA")

    m = _COMPUTE_CAP.search(text)
    if m:
        out._set("min_cuda_compute", float(m.group(1)), "explicit")

    # VRAM first, and its match is then REMOVED from the text before looking
    # for system RAM. "24 GB of GPU memory" contains the word "memory", so a
    # RAM pattern reading the same span sets a 24 GB system-memory floor the
    # user never asked for - a constraint invented out of punctuation.
    remaining = text
    m = _VRAM.search(remaining)
    if m:
        out._set("min_vram_gb", int(next(g for g in m.groups() if g)), "explicit")
        remaining = remaining[:m.start()] + " " + remaining[m.end():]
    m = _RAM.search(remaining)
    if m:
        out._set("min_ram_gb", int(next(g for g in m.groups() if g)), "explicit")

    m = _VCPUS.search(text)
    if m:
        out._set("min_vcpus", int(m.group(1)), "explicit")

    m = _NODES.search(text)
    if m:
        out.count = int(m.group(1))

    return out


_SYSTEM = (
    "You size compute for scientific workloads on the Chameleon testbed. "
    "Given a user's description, state the MINIMUM hardware needed to run it "
    "without failing. Reply with JSON only, using any of these keys: "
    "accelerator (one of cuda, rocm, oneapi, fpga, none), min_cuda_compute, "
    "min_vram_gb, min_ram_gb, min_vcpus, min_tensor_cores. "
    "Omit any key you cannot justify from the description - a guess you cannot "
    "defend is worse than no constraint, because it silently rules out working "
    "hardware. Add a short \"why\" string explaining the sizing."
)


def _llm_infer(workload: str, client) -> Optional[dict]:
    try:
        raw = client.complete(_SYSTEM, workload)
    except Exception as exc:  # noqa: BLE001 - unreachable model is not fatal
        log.warning("spec inference unreachable: %s", exc)
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        log.warning("spec inference returned no JSON object")
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        log.warning("spec inference returned malformed JSON: %s", exc)
        return None


def infer_requirements(workload: str, *, client=None,
                       allow_llm: Optional[bool] = None,
                       intuition=None) -> InferredRequirement:
    """Work out what this job needs. Explicit statements win over inference.

    The LLM is asked only about keys the user did not state, and never
    overrides one they did: a model second-guessing "180 GB or more" is
    replacing a fact with a guess.

    `intuition` is an optional IntuitionStore. Passed in, never discovered:
    it is state exactly like availability, and a run that quietly accumulates
    it stops being comparable to the one before. Given one, past conclusions
    for comparable work are recalled before the model is asked, and anything
    the model does conclude is written back.
    """
    req = extract(workload)

    # What we worked out last time, for keys the user has not stated. Recalled
    # entries rank rather than eliminate, exactly like a fresh inference -
    # remembering a guess does not promote it to a fact.
    recalled_any = False
    if intuition is not None:
        for past in intuition.recall(workload):
            for key, value in past.infers.items():
                if key in req.requires:
                    continue
                state = "confirmed" if past.confirmed else "not since confirmed"
                req._set(key, value, "recalled",
                         f"reused an earlier conclusion for {past.use_case!r}: "
                         f"{key} of {value} ({state})")
                recalled_any = True

    # Recall short-circuits the model. Reusing the reasoning is the point of
    # keeping it - asking again costs a round trip to answer a question that
    # has an answer on file, and two calls about the same job can disagree,
    # which is a worse property than being consistently wrong.
    #
    # The cost: a thin early entry persists until somebody forgets it. That is
    # why `forget` exists and why `confirmed` starts False - revision is
    # deliberate, not whichever answer the model happened to give last.
    if recalled_any:
        return req

    if allow_llm is None:
        allow_llm = os.environ.get("ADVISOR_LLM_SPECS", "false").lower() in {
            "1", "true", "yes", "on"}
    if not allow_llm:
        return req

    if client is None:
        try:
            from ..reason.llm import get_llm_client
            client = get_llm_client()
        except Exception as exc:  # noqa: BLE001
            log.warning("no LLM client for spec inference: %s", exc)
            return req
    if client is None:
        return req

    data = _llm_infer(workload, client)
    if not data:
        return req

    why = str(data.get("why") or "").strip()
    learned_any = False
    for key in ("accelerator", "min_cuda_compute", "min_vram_gb",
                "min_ram_gb", "min_vcpus", "min_tensor_cores"):
        if key not in data or data[key] is None:
            continue
        if key in req.requires:
            continue                      # the user said it; do not overwrite
        value = data[key]
        if key == "accelerator":
            value = str(value).lower()
            if value == "none":
                continue                  # "no accelerator needed" is not a filter
            req._set(key, value, "inferred",
                     f"assumed this needs a {value} accelerator"
                     + (f" ({why})" if why else ""))
            continue
        try:
            raised = round_up_to_fleet(key, float(value))
        except (TypeError, ValueError):
            continue
        as_int = key != "min_cuda_compute"
        stored = int(raised) if as_int else raised
        label = key.replace("min_", "").replace("_", " ")
        if raised > float(value):
            req._set(key, stored, "rounded_up",
                     f"assumed {label} of at least {stored}, raised from an "
                     f"estimated {value} to the next size the testbed has")
        else:
            req._set(key, stored, "inferred",
                     f"assumed {label} of at least {stored}"
                     + (f" ({why})" if why else ""))
        learned_any = True

    # Write back only what the model concluded here. A recall is not a new
    # lesson, and storing it again would let one guess accumulate weight by
    # being repeated rather than by being right.
    if intuition is not None and learned_any:
        intuition.remember(workload, req)
    return req
