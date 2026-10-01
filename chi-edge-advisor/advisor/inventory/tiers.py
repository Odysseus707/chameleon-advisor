"""Capability tiers: how much machine is this, given what we actually measured.

WHY THIS EXISTS, AND WHY capability_score COULD NOT DO IT.

`capability_score` is the testbed's own published ranking rule -
cuda_cores*1 + tensor_cores*4 + ram_gb*8 + vcpus*4 - and it stays exactly as
it is, because the benchmark's golds were solved with it and reproducing them
depends on it. But it cannot answer "is this node enough, and is it more than
enough", because **11 of the 29 bare-metal types score exactly 0**:
compute_zen3, compute_icelake_r750, gpu_pontevecchio and gpu_mi100 among them.
Not because they are weak - a real MI100 is one of the most capable
accelerators at CHI@TACC - but because Blazar reported no ram_gb and no vcpus
for them and R4 forbids inventing the numbers. A summed score turns every
missing measurement into a zero, and a zero sorts as "worst". That is a
measurement gap wearing the costume of a verdict.

A tier is built only from fields that EXIST, so an absent measurement lowers
our confidence rather than the hardware's standing.

WHAT EACH FIELD IS WORTH, measured over the table as it ships:

  accelerator        29/29   the CLASS: cuda / rocm / oneapi / fpga / none
  cuda_compute       10/10   complete for every CUDA type - 3.7 (K80) to 9.0
                             (H100), so CUDA orders itself with no guesswork
  microarchitecture  29/29   but bare "Intel" on 8 of them, which names no
                             generation and must not be treated as one
  ram_gb / vcpus     12/29   refinement INSIDE a tier, never the tier itself

CLASS IS A KIND, NOT A RANK. An MI100 does not satisfy a CUDA requirement at
any tier, and asking whether it "beats" a P100 is not a question with an
answer - the code refuses it rather than resolving it. Cross-class ordering
exists only to lay out a list in a stable order and must never be read as
better-than. That is why this module deliberately does NOT implement __lt__:
`exceeds()` returns None for incomparable pairs, and a caller that wants a
sort order has to ask for `sort_key()` and thereby say that is what it meant.

Generation ordinals are only ever needed where a class holds more than one
type - CUDA (10, all with cuda_compute) and CPU (16, with a named
microarchitecture). rocm, oneapi and fpga hold one type each, so nothing is
invented for them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .catalog import DeviceType

#: Accelerator classes, in a fixed presentation order. This is NOT a ranking:
#: it decides what comes first in a printed list and nothing else. A workload
#: needing ROCm is not better served by anything in the "cuda" bucket.
CLASS_ORDER = ("cuda", "rocm", "oneapi", "fpga", "none")

#: CPU generation ordinals, read off the microarchitecture name the table
#: already carries. The value is the part's release year, which is a fact about
#: the world rather than a judgement about the hardware, and it is only used to
#: order CPUs against each other.
#:
#: DERIVED, in the capability table's own sense of the word: the table states
#: that `microarchitecture` is read off the node_type name, and this is read
#: off that. It is not a measurement and must not be presented as one.
#:
#: Bare "Intel" is deliberately absent. It appears on 8 types and names no
#: generation at all; mapping it to a number would be inventing evidence.
CPU_GENERATION = {
    "intel haswell": 2013.0,
    "intel skylake": 2017.0,
    "intel cascade lake": 2019.0,
    "intel cascade lake (r)": 2019.5,
    "arm neoverse": 2020.0,
    "amd zen 3": 2021.0,
    "intel ice lake": 2021.0,
}


@dataclass(frozen=True)
class Tier:
    """How much machine this is, and how much of that we actually know.

    ``known`` is the load-bearing field. False means nothing beyond the class
    was measured or named, and such a type must be reported as *unranked* -
    never as least capable, which is the specific misreading this module was
    written to prevent.
    """

    machine_type: str
    accel_class: str                     # cuda | rocm | oneapi | fpga | none
    generation: Optional[float] = None   # cuda_compute, or a CPU release year
    generation_label: str = ""           # what the generation was read from
    ram_gb: Optional[int] = None
    vcpus: Optional[int] = None

    @property
    def known(self) -> bool:
        """Do we know anything about this beyond which class it is?"""
        return (self.generation is not None
                or self.ram_gb is not None
                or self.vcpus is not None)

    @property
    def measured(self) -> Tuple[int, int]:
        """RAM/vCPU refinement, with absent treated as 0 FOR ORDERING ONLY.

        Safe here in a way it is not in `meets()`: this only breaks ties inside
        an already-established tier, and `known` carries the fact that the
        numbers are missing. It must never be used to answer whether a node
        satisfies a minimum - that is R4's business and a null fails there.
        """
        return (self.ram_gb or 0, self.vcpus or 0)

    def comparable_to(self, other: "Tier") -> bool:
        """True only within one accelerator class.

        Two types in different classes are different kinds of machine, not two
        points on a scale, and code that wants a "better" between them is
        asking a question with no answer.
        """
        return self.accel_class == other.accel_class

    def exceeds(self, other: "Tier") -> Optional[bool]:
        """Is this strictly more machine than `other`? None if unanswerable.

        None on purpose, in two situations that are both genuinely unanswerable
        rather than merely inconvenient: different classes, and a type we know
        nothing about. Returning False for those would let "we cannot tell"
        read as "no", which is how an unmeasured node quietly becomes the
        weakest option.
        """
        if not self.comparable_to(other):
            return None
        if not self.known or not other.known:
            return None
        if self.generation is not None and other.generation is not None:
            if self.generation != other.generation:
                return self.generation > other.generation
        return self.measured > other.measured

    def sort_key(self) -> tuple:
        """Stable presentation order within a class, least capable first.

        GROUPS by class, it does not rank across them: CPUs are laid out before
        GPUs because a list needs an order, not because a CPU is worse than a
        GPU for every job.

        Only meaningful for types where `known` is True. An unknown type has no
        place on this scale in either direction - first reads as weakest, last
        reads as strongest, and both are claims we cannot support - so use
        `partition()` and present them separately rather than sorting them in.
        """
        try:
            cls = CLASS_ORDER.index(self.accel_class)
        except ValueError:
            cls = len(CLASS_ORDER)
        return (-cls, self.generation or float("-inf"),
                self.measured, self.machine_type)

    def describe(self) -> str:
        """One human-readable phrase, honest about what is missing."""
        if not self.known:
            return (f"{self.accel_class} class; no generation or size measured, "
                    "so it cannot be ranked against the others")
        bits = []
        if self.generation_label:
            bits.append(self.generation_label)
        if self.ram_gb is not None:
            bits.append(f"{self.ram_gb} GB")
        if self.vcpus is not None:
            bits.append(f"{self.vcpus} vCPU")
        if self.ram_gb is None and self.vcpus is None:
            bits.append("size not measured")
        return f"{self.accel_class} class; " + ", ".join(bits)


def tier_for(spec: DeviceType) -> Tier:
    """Build a Tier from a DeviceType, inventing nothing.

    Every value here is copied or read off a field the capability table already
    carries. Where the table says nothing, so does the Tier.
    """
    accel = spec.accelerator or "none"
    generation: Optional[float] = None
    label = ""

    if accel == "cuda" and spec.cuda_compute is not None:
        # Complete for all ten CUDA types, so CUDA needs no fallback at all.
        generation = float(spec.cuda_compute)
        label = f"CUDA compute {spec.cuda_compute}"
    elif accel == "none":
        micro = (spec.microarchitecture or "").strip().lower()
        if micro in CPU_GENERATION:
            generation = CPU_GENERATION[micro]
            label = spec.microarchitecture
        # A bare vendor name ("Intel") names no generation. Left as None.

    return Tier(
        machine_type=spec.machine_type,
        accel_class=accel,
        generation=generation,
        generation_label=label,
        ram_gb=spec.ram_gb,
        vcpus=spec.vcpus,
    )


def partition(tiers):
    """Split into (ranked, unranked). Callers must keep them apart.

    NO bare-metal type lands in `unranked` today. Seven used to - gpu_mi100,
    gpu_pontevecchio, fpga, compute_gigaio, compute_liqid, compute_nvdimm,
    storage_nvme - because Blazar measured no size for them and their
    microarchitecture is a bare vendor name. The reference-API refill measured
    all seven, so the bucket emptied by being answered rather than by being
    abandoned.

    The split stays, because the reason for it does not depend on today's
    coverage. Sorting a type we know nothing about into the ranked list puts it
    at one end or the other, and BOTH ends are a lie: at the front it reads as
    the weakest hardware on the testbed, at the back as the strongest. An
    unmeasured MI100 is neither. It is simply hardware we did not measure, and
    the only honest presentation says so - which is still what happens to any
    row that loses its measurements again.

    `ranked` comes back sorted least-capable-first; `unranked` by name.
    """
    ranked = sorted((t for t in tiers if t.known), key=lambda t: t.sort_key())
    unranked = sorted((t for t in tiers if not t.known),
                      key=lambda t: t.machine_type)
    return ranked, unranked


def smallest_sufficient(tiers, floor: Optional[Tier] = None):
    """The least machine that still clears `floor`, within its class.

    "Slightly overpowered beats underpowered" lives here: given candidates that
    already passed the hard capability filter, prefer the one that clears the
    bar by the smallest margin rather than the largest. Reaching for the
    biggest free node is how one user takes an H100 to run a CPU job while the
    people who need it queue.

    Underpowered never appears: `meets()` has already removed anything that
    fails a requirement, so every candidate here is sufficient by construction.

    Returns None when every candidate is unranked. That is not "no answer
    available" - the caller still has perfectly good hardware - it is "we
    cannot say which of these is the smallest", and the caller should fall back
    to its own ordering rather than treat the absence as a refusal.
    """
    ranked, _unranked = partition(tiers)
    if not ranked:
        return None
    if floor is None:
        return ranked[0]
    for t in ranked:
        if t.comparable_to(floor) and t.exceeds(floor) is not False:
            return t
    return ranked[0]
