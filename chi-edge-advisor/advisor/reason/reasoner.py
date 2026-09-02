"""Reasoner: {workload, availability, inventory, context} -> Recommendation.

Uses the configured LLM client (Tejas Llama by default) to produce a structured
recommendation. If no LLM client/credentials are available -- or the LLM output
can't be parsed -- it falls back to a deterministic, fully explainable
heuristic so the pipeline always yields a checkable recommendation offline.
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from ..artifacts.registry import ARTIFACTS_BY_ID
from ..artifacts.router import RetrievalResult
from ..availability.base import DeviceAvailability
from ..inventory.catalog import DeviceType
from .llm import LLMClient, get_llm_client
from .schema import Recommendation

# What the model is told. Deliberately absent: any ranking rule, scoring weight
# or requirement threshold. The inventory block states what each device IS;
# working out what the workload NEEDS, and which devices therefore qualify, is
# the reasoning being measured and must not be handed over here.
SYSTEM_PROMPT = (
    "You are an allocation-aware resource advisor for Chameleon Cloud's "
    "CHI@Edge testbed. Recommend exactly one concrete device and a runnable "
    "lease configuration for the user's workload. You MUST ground your choice "
    "in the provided artifact context and respect the live availability and "
    "static inventory given. CHI@Edge traps to avoid: match architecture "
    "(arm64 vs x86_64); only pick a device that is free in the requested "
    "window; machine_type/device_profile strings must exist in inventory; "
    "always set platform_version; set runtime='nvidia' for GPU workloads on "
    "Jetson devices. "
    "A device being free is not sufficient. Read the workload for the hardware "
    "it actually requires - accelerator, compute capability, numeric precision, "
    "memory, attached peripherals - and rule out every device type in the "
    "inventory that does not meet those requirements, however available it is. "
    "Not every accelerator is interchangeable: an Edge TPU runs int8-quantised "
    "TFLite only and cannot run CUDA code. "
    "If no artifact in the context documents the device type you choose, say so "
    "in `reasoning` rather than implying the configuration is validated. "
    "Respond with ONLY a JSON object, no prose, with keys: "
    "machine_type, device_name (or null), count, duration_hours, architecture, "
    "image, device_profiles (list), platform_version, runtime (or null), "
    "exposed_ports (list), gpu (bool), reasoning."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> Optional[dict]:
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


class Reasoner:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        allow_heuristic_fallback: bool = True,
    ):
        self._explicit_client = llm_client
        self.allow_heuristic_fallback = allow_heuristic_fallback

    def _client(self) -> Optional[LLMClient]:
        if self._explicit_client is not None:
            return self._explicit_client
        try:
            return get_llm_client()
        except Exception:  # noqa: BLE001 - missing SDK/creds
            return None

    # -- prompt -----------------------------------------------------------
    @staticmethod
    def _availability_block(availability: List[DeviceAvailability]) -> str:
        if not availability:
            return "(no live availability data)"
        lines = []
        for d in availability[:40]:
            free = (
                "free" if d.free_now
                else "reserved" if d.free_now is False
                else "unknown"
            )
            lines.append(
                f"- {d.device_uid} type={d.machine_type} arch={d.architecture} "
                f"gpu={d.gpu} state={free}"
            )
        if len(availability) > 40:
            lines.append(f"- ... and {len(availability) - 40} more devices")
        return "\n".join(lines)

    @staticmethod
    def _inventory_block(inventory: List[DeviceType]) -> str:
        """The device catalogue, with hardware capability.

        Capability is the half of the decision live availability cannot answer:
        a free device that cannot run the workload is still the wrong answer.
        Blazar reports none of it, so if these fields are not rendered here the
        model sees only `gpu=True` and a jetson-nano is indistinguishable from
        an AGX Orin. Every field below is a vendor fact; how to weigh them is
        left to the model on purpose.
        """
        lines = []
        for dt in inventory:
            spec = [f"- {dt.machine_type} arch={dt.architecture}"]
            spec.append(f"accelerator={dt.accelerator or 'unknown'}")
            if dt.accelerator == "cuda":
                spec.append(f"cuda_compute={dt.cuda_compute} "
                            f"cuda_cores={dt.cuda_cores} "
                            f"tensor_cores={dt.tensor_cores}")
            elif dt.accelerator == "edgetpu":
                spec.append(f"edge_tpu_tops={dt.edge_tpu_tops} (int8 TFLite only; "
                            f"CUDA code will NOT run on it)")
            if dt.ram_gb is not None:
                spec.append(f"ram_gb={dt.ram_gb}")
            if dt.precisions:
                spec.append(f"precisions={dt.precisions}")
            if dt.peripherals:
                spec.append(f"peripherals={dt.peripherals}")
            spec.append(f"profiles={dt.device_profiles}")
            spec.append(f"runtime={dt.runtime}")
            spec.append(f"platform_version={dt.platform_version}")
            lines.append(" ".join(spec))
        return "\n".join(lines)

    def build_user_prompt(
        self,
        workload: str,
        availability: List[DeviceAvailability],
        inventory: List[DeviceType],
        retrieval: RetrievalResult,
    ) -> str:
        return (
            f"WORKLOAD:\n{workload}\n\n"
            f"LIVE AVAILABILITY:\n{self._availability_block(availability)}\n\n"
            f"STATIC INVENTORY:\n{self._inventory_block(inventory)}\n\n"
            f"RELEVANT ARTIFACT CONTEXT (grounded_by="
            f"{retrieval.provenance}):\n{retrieval.context_text}\n\n"
            "Return the JSON recommendation now."
        )

    # -- main -------------------------------------------------------------
    def recommend(
        self,
        workload: str,
        availability: List[DeviceAvailability],
        inventory: List[DeviceType],
        retrieval: RetrievalResult,
    ) -> Recommendation:
        client = self._client()
        if client is not None:
            user = self.build_user_prompt(workload, availability, inventory, retrieval)
            try:
                raw = client.complete(SYSTEM_PROMPT, user)
                data = _extract_json(raw)
                if data is not None:
                    rec = Recommendation.from_dict(data)
                    rec.produced_by = client.name
                    if not rec.grounded_by:
                        rec.grounded_by = list(retrieval.provenance)
                    return rec
            except Exception:  # noqa: BLE001 - fall through to heuristic
                pass
            if not self.allow_heuristic_fallback:
                raise RuntimeError("LLM reasoning failed and heuristic fallback is off.")
        elif not self.allow_heuristic_fallback:
            raise RuntimeError("No LLM client available and heuristic fallback is off.")
        return self._heuristic(workload, availability, inventory, retrieval)

    # -- deterministic fallback ------------------------------------------
    @staticmethod
    def _parse_request(text: str) -> "tuple[int | None, float | None]":
        """Pull the requested device count and lease length out of the question.

        Returns (count, hours), either of which may be None when the user did not
        say. Callers keep their own defaults for that case rather than inventing a
        number the user never asked for.
        """
        import re

        words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
        unit_hours = {"minute": 1 / 60, "min": 1 / 60,
                      "hour": 1.0, "hr": 1.0, "day": 24.0, "week": 168.0}

        count = None
        # Allow a few words between the number and the noun so that phrasing like
        # "40 raspberry pi devices" is not read as a request for one device.
        m = re.search(r"(\d+)\s*(?:x\s*)?(?:[a-z0-9-]+\s+){0,3}?"
                      r"(?:device|node|board|pi|unit)s?\b", text, re.I)
        if m:
            count = int(m.group(1))
        else:
            for word, n in words.items():
                if re.search(rf"\b{word}\s+(?:device|node|board|pi|unit)s?\b", text, re.I):
                    count = n
                    break

        hours = None
        m = re.search(r"(\d+(?:\.\d+)?)\s*(minute|min|hour|hr|day|week)s?\b", text, re.I)
        if m:
            hours = float(m.group(1)) * unit_hours[m.group(2).lower()]
        return count, hours

    # -- workload requirement inference -----------------------------------
    # Deliberately keyword-driven and deliberately crude. The benchmark's gold
    # solver reads a machine-readable `requires` dict off each item; the advisor
    # never sees that and must recover intent from the sentence a user typed.
    # Keeping this simple is the point - it is the declared floor, and if it
    # matched the solver the comparison would measure nothing.
    _REQ_PATTERNS = (
        # (regex, field, value)
        (r"tensor\s*core|tensorrt", "accelerator", "cuda"),
        (r"tensor\s*core", "tensor_cores", "required"),
        (r"\bcuda\b|\bgpu\b|gpu-accelerat", "accelerator", "cuda"),
        (r"edge\s*tpu|coral", "accelerator", "edgetpu"),
        (r"on the cpu|cpu[- ]only|cpu inference|on cpu", "accelerator", "none"),
        (r"\bint8\b|quantiz", "precision", "int8"),
        (r"\bfp16\b|half[- ]precision", "precision", "fp16"),
        (r"sense\s*hat", "peripheral", "sense_hat"),
        (r"camera|picamera|video", "peripheral", "camera"),
        (r"\bgpio\b|sensor", "peripheral", "gpio"),
    )

    @staticmethod
    def _infer_requirements(text: str) -> dict:
        """What the workload needs, read off the request itself."""
        req: dict = {}
        low = text.lower()
        for pat, field_, value in Reasoner._REQ_PATTERNS:
            if re.search(pat, low) and field_ not in req:
                req[field_] = value
        m = re.search(r"(\d+)\s*gb\b", low)
        if m:
            req["min_ram_gb"] = int(m.group(1))
        return req

    @staticmethod
    def _meets(dt: DeviceType, req: dict) -> "list[str]":
        """Why `dt` fails `req`, or an empty list if it qualifies."""
        why = []
        want = req.get("accelerator")
        if want and (dt.accelerator or "none") != want:
            why.append(f"accelerator={dt.accelerator or 'none'}, needs {want}")
        prec = req.get("precision")
        if prec and prec not in (dt.precisions or []):
            why.append(f"no {prec}")
        per = req.get("peripheral")
        if per and per not in (dt.peripherals or []):
            why.append(f"no {per}")
        if req.get("tensor_cores") and not dt.tensor_cores:
            why.append("no tensor cores")
        ram = req.get("min_ram_gb")
        if ram is not None and (dt.ram_gb or 0) < ram:
            why.append(f"{dt.ram_gb}GB < {ram}GB")
        return why

    @staticmethod
    def _heuristic(
        workload: str,
        availability: List[DeviceAvailability],
        inventory: List[DeviceType],
        retrieval: RetrievalResult,
    ) -> Recommendation:
        """Explainable non-LLM recommendation driven by artifact provenance."""
        import os
        # Defaults ON. With it off the advisor ignores live state in three ways
        # that each produce an unsubmittable spec: a type with nothing free stays
        # a candidate (provenance outranks free-ness in rank_key), a busy device
        # can be named, and the parsed count/duration are discarded for a
        # hardcoded 1 device / 3 hours. Set ADVISOR_STATE_AWARE=0 to reproduce
        # arms collected before this default changed - results either side of it
        # are not comparable.
        state_aware = os.environ.get("ADVISOR_STATE_AWARE", "true").lower() in {
            "1", "true", "yes", "on"}

        # Every (artifact, machine_type) the retrieval actually grounds, in rank
        # order. This is where the IMAGE and the device_profiles come from - a
        # configuration is only trustworthy if some artifact demonstrated it.
        pairs = [(pid, pmeta, mt)
                 for pid in retrieval.provenance
                 if (pmeta := ARTIFACTS_BY_ID.get(pid))
                 for mt in pmeta.machine_types]
        covered = {mt: (pid, pmeta) for pid, pmeta, mt in reversed(pairs)}

        free_by_type = {}
        for d in availability:
            if d.free_now:
                free_by_type.setdefault(d.machine_type, []).append(d)

        # Candidates are the whole catalogue, not just the artifact-covered
        # corner of it. Selecting only from provenance capped the advisor at the
        # two types the seeded artifacts happen to document, so five of the seven
        # device types on the site could never be recommended however well they
        # fit - including every accelerator.
        req = Reasoner._infer_requirements(workload)
        qualified, rejected = [], []
        for dt in inventory:
            why = Reasoner._meets(dt, req)
            if why:
                rejected.append((dt.machine_type, "; ".join(why)))
            else:
                qualified.append(dt)

        # Ordering policy, and it is ours, not the benchmark's: prefer a type an
        # artifact actually documents, then one that is free, then the SMALLEST
        # part that satisfies the request, so a scarce high-end device is not
        # consumed by a workload a common one can run. The gold solver ranks by
        # free count and then by most capable; keeping these different is what
        # stops the comparison measuring agreement with a tie-break.
        def rank_key(dt):
            return (
                0 if dt.machine_type in covered else 1,
                0 if free_by_type.get(dt.machine_type) else 1,
                dt.ram_gb or 0,
                dt.cuda_cores,
                dt.machine_type,
            )

        ordered = sorted(qualified, key=rank_key)
        # Only filter when live state was actually observed. An empty or
        # all-unknown availability list means "we don't know what is free", not
        # "nothing is free" - advisor_room swallows backend failures into [], and
        # the reference_api backend carries no CHI@Edge inventory at all.
        # Filtering on absent state would answer "nothing fits" to every question.
        # See DeviceAvailability: free_now is None is unknown, never free.
        # free_now is None IS the definition of unknown (see DeviceAvailability),
        # so ask that directly rather than the live_state_known bookkeeping flag:
        # callers that populate free_now from a real snapshot do not always set
        # the flag, and trusting it silently disables filtering on exactly the
        # inputs that carry the most state.
        have_live_state = any(d.free_now is not None for d in availability)
        blocked_by_state = []
        if state_aware and have_live_state:
            # A type with nothing free cannot be reserved, so it is not a
            # candidate at all - not merely a worse one.
            free_types = [d for d in ordered if free_by_type.get(d.machine_type)]
            # Keep what capability admitted but availability removed. "Nothing
            # can do this" and "everything that can is busy" are different
            # answers to different questions, and collapsing them into one
            # reports a capability limit where the real limit is the clock.
            blocked_by_state = [d for d in ordered if d not in free_types]
            ordered = free_types

        top = ordered[0] if ordered else None
        machine_type = top.machine_type if top else ""

        def not_weaker(d, t):
            """An alternative must not be worse than the top pick on anything
            the top pick provides.

            Requirements were inferred from a sentence, so they under-approximate
            what the user needs: R37 asks for a notebook server and means 8GB
            without saying so. Offering a smaller or less capable part as the
            fallback is how a crude filter becomes a wrong recommendation, so
            rank 2 and 3 must clear the bar rank 1 already cleared.
            """
            return ((d.ram_gb or 0) >= (t.ram_gb or 0)
                    and set(d.precisions or []) >= set(t.precisions or [])
                    and set(d.peripherals or []) >= set(t.peripherals or [])
                    and set(d.device_profiles or []) >= set(t.device_profiles or []))

        alternatives = [d.machine_type for d in ordered[1:]
                        if free_by_type.get(d.machine_type) and not_weaker(d, top)][:2]
        aid, meta = covered.get(machine_type, (None, None))
        switched_from = None

        inv = {d.machine_type: d for d in inventory}
        dt = inv.get(machine_type)
        # The device type is authoritative about the hardware; the artifact is
        # authoritative only about the image it was demonstrated with. Reading
        # architecture off the artifact would describe the machine it ran on
        # rather than the one being recommended.
        architecture = (dt.architecture if dt else None) or (
            meta.architecture if meta else "arm64"
        )
        gpu = bool(dt.gpu) if dt else bool(meta.gpu if meta else False)
        runtime_needed = (dt.runtime if dt else None)

        candidates = [d for d in availability if d.machine_type == machine_type]
        free = [d for d in candidates if d.free_now]
        if state_aware:
            # Never name a device that is not free: a busy or down device yields
            # a spec that cannot be submitted.
            device_name = free[0].device_uid if free else None
        else:
            chosen_pool = free or candidates
            device_name = chosen_pool[0].device_uid if chosen_pool else None

        # How many, and for how long. Previously both were hardcoded (1 device,
        # 3 hours) so the answer ignored what the user actually asked for.
        req_count, req_hours = Reasoner._parse_request(workload)
        count = (req_count or 1) if state_aware else 1
        duration_hours = (req_hours or 3) if state_aware else 3

        # A default the user never asked for must not read like a recommendation.
        # Naming it as an assumption is the difference between a usable answer and
        # a confident invention.
        assumed = []
        if state_aware and req_count is None:
            assumed.append(f"{count} device" + ("s" if count != 1 else ""))
        if state_aware and req_hours is None:
            assumed.append(f"{duration_hours:g} h")
        assume_note = ""
        if assumed:
            assume_note = ("You did not say how many or for how long, so this assumes "
                           + " for ".join(assumed)
                           + " - give a count and a duration and this can be redone. ")

        count_note = ""
        if state_aware and free_by_type and count > len(free):
            count_note = (f"Requested {count} devices but only {len(free)} of "
                          f"{machine_type} are free right now. ")

        hold_note = ""
        if state_aware and device_name:
            # available_hours is None when nothing is booked after this device,
            # so None means unbounded here, not unknown.
            hold = free[0].available_hours if free else None
            if hold is not None and hold < duration_hours:
                hold_note = (f"It is free for only {hold:.1f} h, short of the "
                             f"{duration_hours:g} h requested. ")
            else:
                hold_note = (f"Hold it for the {duration_hours:g} h requested; no "
                             f"later reservation blocks it. ")

        runtime = runtime_needed or ("nvidia" if gpu else None)
        exposed_ports = [22] if (meta and meta.artifact_id == "edge_ssh_image") else []

        # No device type satisfies the request. Saying so is the answer; naming
        # a near-miss anyway is the failure mode the infeasible items exist to
        # catch.
        if not machine_type:
            if blocked_by_state:
                # Capability is satisfied; only the clock is in the way. Saying
                # "nothing satisfies this request" here would report a hardware
                # limit that does not exist, and would send the user away from a
                # testbed that will suit them perfectly in an hour.
                busy_types = sorted({d.machine_type for d in blocked_by_state})
                when = sorted(
                    d.reserved_until for d in availability
                    if d.machine_type in set(busy_types) and d.reserved_until)
                free_at = f" Earliest one frees at {when[0]}." if when else ""
                return Recommendation(
                    machine_type="", count=count, duration_hours=duration_hours,
                    architecture="arm64", image="",
                    reasoning=("Heuristic (no LLM): every device type that suits this "
                               f"request is busy right now - {', '.join(busy_types)}. "
                               "This is an availability limit, not a capability one: "
                               "the hardware exists and fits, it is reserved."
                               f"{free_at} Requirements read from the request: "
                               f"{req or 'none'}."),
                    alternatives=busy_types,
                    gpu=False, site="CHI@Edge", api_family="edge",
                    grounded_by=list(retrieval.provenance), produced_by="heuristic",
                )
            unmet = ", ".join(f"{n} ({w})" for n, w in sorted(rejected))
            return Recommendation(
                machine_type="", count=count, duration_hours=duration_hours,
                architecture="arm64", image="",
                reasoning=("Heuristic (no LLM): nothing on CHI@Edge satisfies this "
                           f"request. Requirements read from the request: {req or 'none'}. "
                           f"Not recommended: {unmet}."),
                gpu=False, site="CHI@Edge", api_family="edge",
                grounded_by=list(retrieval.provenance), produced_by="heuristic",
            )

        req_note = (f"Requirements read from the request: {req}. " if req else "")
        reject_note = ""
        if rejected:
            reject_note = ("Not recommended: "
                           + "; ".join(f"{n} ({w})" for n, w in sorted(rejected))
                           + ". ")
        # An answer that names hardware no artifact demonstrates must say so.
        # The alternative is a configuration that reads as validated when nothing
        # in the corpus has ever run it.
        coverage_note = (
            "" if meta else
            f"No Trovi artifact documents {machine_type}, so no container image, "
            f"device_profile or runtime for it is grounded in the corpus; anything "
            f"named here would be unvalidated. "
        )

        reason = (
            (f"Heuristic (no LLM): workload routed to artifact '{aid}' -> "
             f"machine_type {machine_type} ({architecture}"
             f"{', gpu' if gpu else ''}). " if aid else
             f"Heuristic (no LLM): machine_type {machine_type} ({architecture}"
             f"{', gpu' if gpu else ''}) selected from the device catalogue. ")
            + req_note
            + (
                f"Switched from {switched_from} (no free device) to {machine_type} "
                f"on live availability. " if switched_from else ""
            )
            + (
                f"Selected free device {device_name}. "
                if device_name and free
                else "No live-free device confirmed; verify availability. "
            )
            + assume_note
            + count_note
            + hold_note
            + coverage_note
            + reject_note
            + (f"Image {meta.image} from the grounded artifact."
               if meta else "No grounded image to offer.")
        )
        # Site and grammar come from the catalog, which observed them from
        # Blazar. Never inferred from the machine_type string: a wrong
        # api_family renders a spec that fails at submission.
        site = dt.sites[0] if dt and dt.sites else (meta.site if meta else None)
        api_family = dt.api_family if dt else "edge"

        return Recommendation(
            machine_type=machine_type,
            count=count,
            duration_hours=duration_hours,
            architecture=architecture,
            image=meta.image if meta else "",
            reasoning=reason,
            device_name=device_name,
            device_profiles=list(meta.device_profiles) if meta else [],
            platform_version=dt.platform_version if dt else 2,
            runtime=runtime,
            exposed_ports=exposed_ports,
            gpu=gpu,
            site=site,
            api_family=api_family,
            alternatives=alternatives,
            grounded_by=list(retrieval.provenance),
            produced_by="heuristic",
        )
