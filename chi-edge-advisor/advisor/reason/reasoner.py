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

SYSTEM_PROMPT = (
    "You are an allocation-aware resource advisor for Chameleon Cloud's "
    "CHI@Edge testbed. Recommend exactly one concrete device and a runnable "
    "lease configuration for the user's workload. You MUST ground your choice "
    "in the provided artifact context and respect the live availability and "
    "static inventory given. CHI@Edge traps to avoid: match architecture "
    "(arm64 vs x86_64); only pick a device that is free in the requested "
    "window; machine_type/device_profile strings must exist in inventory; "
    "always set platform_version; set runtime='nvidia' for GPU workloads on "
    "Jetson devices. Respond with ONLY a JSON object, no prose, with keys: "
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
        return "\n".join(lines)

    @staticmethod
    def _inventory_block(inventory: List[DeviceType]) -> str:
        lines = []
        for dt in inventory:
            lines.append(
                f"- {dt.machine_type} arch={dt.architecture} gpu={dt.gpu} "
                f"profiles={dt.device_profiles} runtime={dt.runtime} "
                f"platform_version={dt.platform_version}"
            )
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

    @staticmethod
    def _heuristic(
        workload: str,
        availability: List[DeviceAvailability],
        inventory: List[DeviceType],
        retrieval: RetrievalResult,
    ) -> Recommendation:
        """Explainable non-LLM recommendation driven by artifact provenance."""
        import os
        state_aware = os.environ.get("ADVISOR_STATE_AWARE", "false").lower() in {
            "1", "true", "yes", "on"}

        # Every (artifact, machine_type) the retrieval actually grounds, in rank
        # order. Capability comes from here and only here: availability may
        # filter this list but must never add a type no artifact supports.
        pairs = [(pid, pmeta, mt)
                 for pid in retrieval.provenance
                 if (pmeta := ARTIFACTS_BY_ID.get(pid))
                 for mt in pmeta.machine_types]
        aid, meta, machine_type = pairs[0] if pairs else (None, None, "raspberrypi4-64")

        free_by_type = {}
        for d in availability:
            if d.free_now:
                free_by_type.setdefault(d.machine_type, []).append(d)

        # The state-blind path fixed machine_type from provenance[0] and only
        # then looked at availability, so the pick never moved with the site.
        switched_from = None
        if state_aware and free_by_type and machine_type not in free_by_type:
            for pid, pmeta, mt in pairs:
                if mt in free_by_type:
                    switched_from = machine_type
                    aid, meta, machine_type = pid, pmeta, mt
                    break

        inv = {dt.machine_type: dt for dt in inventory}
        dt = inv.get(machine_type)
        architecture = (meta.architecture if meta else None) or (
            dt.architecture if dt else "arm64"
        )
        gpu = bool(meta.gpu) if meta else bool(dt.gpu if dt else False)

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

        runtime = "nvidia" if gpu else None
        exposed_ports = [22] if (meta and meta.artifact_id == "edge_ssh_image") else []

        reason = (
            f"Heuristic (no LLM): workload routed to artifact "
            f"'{aid}' -> machine_type {machine_type} ({architecture}"
            f"{', gpu' if gpu else ''}). "
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
            + f"Image {meta.image if meta else 'n/a'} from the grounded artifact."
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
            grounded_by=list(retrieval.provenance),
            produced_by="heuristic",
        )
