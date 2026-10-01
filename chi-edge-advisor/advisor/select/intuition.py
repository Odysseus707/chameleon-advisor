"""What the advisor has learned about sizing use cases.

The inference layer works out specs from a request. This is where those
conclusions persist, so the second person to ask for a 7B fine-tune benefits
from the reasoning done for the first.

WHAT THIS IS, AND WHAT IT IS EMPHATICALLY NOT.

It records a claim about what a WORKLOAD NEEDS. The capability table records
what HARDWARE CAN DO. Those are different kinds of claim with different
provenance, and merging them would destroy the one property the whole system is
built on - being able to say which half of a verdict was measured and which was
asserted (R3). Nothing here is ever written into the capability table, and
nothing here is ever written into the grounding corpus either: a model's guess
must stay distinguishable from a pinned Trovi artifact (R2).

A RECALLED INTUITION IS STILL A GUESS. It carries exactly the authority of the
inference that produced it, which is to say it ranks and does not eliminate.
Recalling it does not launder it into a fact - if anything the opposite, since
a wrong entry now repeats itself confidently, so the origin is labelled
`recalled` and the assumption text says where it came from and whether anyone
ever confirmed it.

REPRODUCIBILITY. This is state, exactly like availability, and a benchmark run
that silently accumulates it stops being comparable to the one before. So it is
injected, never discovered: `infer_requirements` takes a store or takes None,
and nothing here reaches for a default path on its own. A pinned store makes a
collected run repeatable; no store makes it stateless.

NO AUTHOR FIELD. Deliberately. Which model produced a guess is not evidence
about the guess, and recording it invites the reader to weigh entries by
by-line rather than by whether anyone confirmed them.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")

#: Overlap needed before two use cases count as the same kind of job. Two
#: distinct shared tokens. One is far too cheap - "model" or "run" would recall
#: an unrelated entry for most requests, and a memory that always fires is
#: indistinguishable from no memory at all.
MIN_OVERLAP = 2

#: Words carrying no signal about what a job needs. Left out of matching so
#: they cannot be two of the two tokens that make a match.
_STOP = frozenset("""a an the i to on in for of and or with my me need want
run running use using please help how do does can could would should node
nodes about hour hours job get""".split())


def _tokens(text: str) -> set:
    return {t for t in _TOKEN.findall((text or "").lower())
            if t not in _STOP and len(t) > 1}


@dataclass
class Intuition:
    """One learned mapping from a kind of work to the specs it needs."""

    id: str
    use_case: str
    infers: Dict
    taught_by: str
    recorded_utc: str
    confirmed: bool = False
    rounded_up: bool = False

    def describe(self) -> str:
        state = "confirmed" if self.confirmed else "never confirmed"
        return (f"a previous request for {self.use_case!r} was sized as "
                f"{self.infers} ({state})")


class IntuitionStore:
    """A file of Intuitions, recalled by how similar the request is.

    Deliberately not an embedding index. Recall has to be identical on every
    run for a pinned store to mean anything, and token overlap is exactly
    reproducible where a model-backed nearest-neighbour is only nearly so. The
    corpus this searches is small and written in the user's own words, which is
    the case where lexical matching is strongest.
    """

    def __init__(self, records: Optional[List[Intuition]] = None):
        self.records: List[Intuition] = list(records or [])

    # -- persistence -------------------------------------------------------
    @classmethod
    def load(cls, path: Path) -> "IntuitionStore":
        """Read a store. A missing file is an empty store, not an error."""
        path = Path(path)
        if not path.is_file():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Loud, and empty. Continuing with a half-parsed memory would be
            # worse than continuing with none.
            log.warning("intuition store unreadable (%s); starting empty", exc)
            return cls()
        out = []
        known = set(Intuition.__dataclass_fields__)
        for d in raw.get("intuitions", []):
            try:
                out.append(Intuition(**{k: v for k, v in d.items() if k in known}))
            except TypeError as exc:
                log.warning("skipping malformed intuition %r: %s", d.get("id"), exc)
        return cls(out)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"version": "1.0", "intuitions": [asdict(r) for r in self.records]},
            indent=2))
        return path

    # -- writing -----------------------------------------------------------
    def remember(self, workload: str, requirement, *,
                 now: Optional[datetime] = None) -> Optional[Intuition]:
        """Record what was inferred here. Returns None if nothing was.

        Only the INFERRED part is kept. What the user stated is theirs, not
        something the advisor worked out, and storing it would let a stranger's
        explicit "180 GB" come back later as our assumption about somebody
        else's job.
        """
        learned = {k: v for k, v in requirement.requires.items()
                   if requirement.origin.get(k) in {"inferred", "rounded_up"}}
        if not learned:
            return None

        stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        existing = self._exact(workload)
        if existing is not None:
            # Same question asked twice. Update in place rather than letting
            # duplicates accumulate and outvote a later correction.
            existing.infers = learned
            existing.recorded_utc = stamp
            existing.rounded_up = requirement.rounded_up
            return existing

        rec = Intuition(
            id="li_%04d" % (len(self.records) + 1),
            use_case=workload.strip(),
            infers=learned,
            taught_by=workload.strip(),
            recorded_utc=stamp,
            confirmed=False,
            rounded_up=requirement.rounded_up,
        )
        self.records.append(rec)
        return rec

    def confirm(self, intuition_id: str) -> bool:
        """Mark an entry as borne out. The only way `confirmed` becomes True -
        nothing sets it on the way in."""
        for r in self.records:
            if r.id == intuition_id:
                r.confirmed = True
                return True
        return False

    def forget(self, intuition_id: str) -> bool:
        """Drop an entry. A memory with no way to be wrong is a liability."""
        before = len(self.records)
        self.records = [r for r in self.records if r.id != intuition_id]
        return len(self.records) < before

    # -- reading -----------------------------------------------------------
    def _exact(self, workload: str) -> Optional[Intuition]:
        w = (workload or "").strip().lower()
        return next((r for r in self.records if r.use_case.lower() == w), None)

    def recall(self, workload: str, k: int = 3) -> List[Intuition]:
        """Past entries for comparable work, best match first.

        Ties break on confirmed-before-unconfirmed, then on recency, then on id
        so the order is total and a pinned store recalls identically forever.
        """
        want = _tokens(workload)
        if not want:
            return []
        scored = []
        for r in self.records:
            overlap = len(want & _tokens(r.use_case))
            if overlap >= MIN_OVERLAP:
                scored.append((-overlap, not r.confirmed, _neg(r.recorded_utc),
                               r.id, r))
        scored.sort(key=lambda t: t[:4])
        return [t[4] for t in scored[:k]]

    def __len__(self) -> int:
        return len(self.records)


def _neg(stamp: str) -> str:
    """Sort key putting newer timestamps first, without parsing them.

    ISO-8601 sorts lexically, so inverting each character's ordinal gives a
    descending sort that never raises on a malformed stamp - a memory should
    not fall over because one entry has a bad date.
    """
    return "".join(chr(0x10FFFF - ord(c)) if ord(c) < 0x10FFFF else c
                   for c in (stamp or ""))
