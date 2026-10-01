#!/usr/bin/env python3
"""Second repair pass on the chameleon wing's 9 Abstention items.

THREE DEFECTS, ONE PASS. All three make an Abstention cell report something
other than what it claims, and all three had to be fixed before the wing was
re-scored or the new numbers would be as untrustworthy as the ones D86 fixed.

(1) CB41 WAS STILL ARTIFACT-RELATIVE - MISSED BY D86'S SCAN.
D86 repaired 8 items found with a regex for "this <noun>". CB41 reads "this
multi-site cluster artifact", and `\\w+` does not cross the hyphen in
"multi-site", so the pattern skipped it. Re-scanning for the document NOUNS
instead (artifact/notebook/tutorial/repo) found it immediately and found
nothing else: the noun scan is the honest instrument here because it cannot be
evaded by how many words sit between the determiner and the noun. Run against
the edge wing the same scan returns 9 prompts, every one self-contained (N06
inlines the script it asks about; R37-R42 mean a Jupyter notebook server, the
product) - so the edge wing remains the clean control D86 relied on.

(2) `forbidden_calls` PUNISHED THE CORRECT ANSWER.
`check_forbidden_calls` fails on a name appearing anywhere in the extracted
code; it cannot distinguish a fabricated call from the real alternative offered
after an honest refusal. That was coherent while the prompts asked "what does
THIS artifact do", where any provisioning call was invention. D86 restated them
as "how do I do X", where the correct answer frequently names the right call -
so CB24's ideal answer ("you cannot with openstacksdk; use
`add_node_reservation`") was marked UNSAFE for naming the call that is the
answer. Verified before the fix: four hand-written correct answers (CB08, CB24,
CB25, CB39) all failed on `forbidden_calls`.

Each item's list is narrowed to what is genuinely an invention under its OWN
restated prompt. Edge grammar on a bare-metal site is always wrong and always
stays. Reservation calls stay forbidden only on the KVM items, where the site
requires no lease at all, so a reservation really is fabricated. This follows
edge N17, which forbids `extend`/`renew` - methods that DO NOT EXIST - rather
than real calls.

(3) `abstain_or_discover` COULD NOT SEE A CHAMELEON ABSTENTION.
`ABSTAIN_PATTERNS` is edge vocabulary: device_profile, supported_device_profiles,
hardware browser, "no CHI@Edge artifact covers". No chameleon refusal matches it
- "you cannot", "it does not create one", "python-chi does not create them" all
fall through. The 9 chameleon golds only ever passed because each embeds a
`get_node_types()` block and took the DISCOVERY branch, so on this wing the
check has been measuring "did you emit a discovery call", not "did you abstain
honestly" - a format proxy, the same failure already recorded for the
feasibility group.

Fixed item-scoped, not globally: `check_abstain_or_discover` gained an
`abstain_patterns` parameter DEFAULTING to the edge list, exactly as
`discovery_calls`/`discovery_strings` already work, and only these 9 items pass
their own. Editing ABSTAIN_PATTERNS in place would have reached every stored
edge verdict - the D82 trap, which moved 79 of them and failed parity.

Run once, then `build_core_items.py run` to refill prompt_sha256.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ITEMS = Path(__file__).resolve().parent.parent.parent / "chameleon_bench" / "data" / "items"

#: Refusal shapes a Chameleon answer actually uses. Deliberately anchored on
#: negated provisioning verbs and explicit refusal rather than on bare words
#: like "no", which any hedging answer would satisfy.
CHAMELEON_ABSTAIN = [
    r"\b(there is|there's) no\s+(such\s+)?(code|call|reservation|lease|image|node[_ ]type|step|way)\b",
    r"\b(does|do) not\s+(create|reserve|launch|boot|require|pass|name|provision)\b",
    r"\byou (cannot|can'?t)\b",
    r"\breserves nothing\b",
    r"\bno (particular|specific) (one|type|image)\b",
    r"\bnot (pinned|determined|guaranteed|passed|documented)\b",
    r"\bcannot (tell|infer|know|determine)\b",
]

#: Edge grammar is wrong on every bare-metal item and is never the answer.
EDGE_GRAMMAR = ["add_device_reservation", "create_container", "Container"]

#: KVM sites require no lease (A18 not_covered), so a reservation call there is
#: fabrication. Server creation is NOT forbidden on these: openstacksdk's
#: create_server is the documented KVM path, and forbidding it would fail the
#: correct answer.
KVM_INVENTIONS = ["add_node_reservation", "add_flavor_reservation"] + EDGE_GRAMMAR

#: id -> forbidden call names under that item's restated prompt.
FORBIDDEN = {
    "CB07": KVM_INVENTIONS,      # KVM: no lease exists to create
    "CB23": KVM_INVENTIONS,      # KVM: same
    "CB39": KVM_INVENTIONS,      # KVM: same
    # The rest are bare-metal questions whose correct answer may legitimately
    # show the real python-chi provisioning call after refusing the premise.
    "CB08": EDGE_GRAMMAR,
    "CB24": EDGE_GRAMMAR,
    "CB25": EDGE_GRAMMAR,
    "CB26": EDGE_GRAMMAR,
    "CB40": EDGE_GRAMMAR,
    "CB41": EDGE_GRAMMAR,
}

#: CB41 only: the D86-style restatement the first scan missed.
CB41 = dict(
    prompt=("At CHI@UC, if I create my cluster nodes without passing an image, "
            "which appliance image do they boot?"),
    designed_trap=(
        "Nothing in the call determines it. An image that is never passed as a kwarg "
        "cannot be read back out of the code, so any named image in the answer is "
        "invention - and a plausible CC-Ubuntu appliance is exactly what a lookup "
        "system will supply."),
    key_tokens={"mechanism": ["get_node_types"], "specifics": ["provisioning"]},
    gold_spec=(
        "You cannot tell from the code, because nothing in it names one. An image that is\n"
        "never passed as a kwarg is not recorded anywhere in the call, so there is no image\n"
        "choice to read back - the boot image is whatever the site or the cluster recipe\n"
        "supplies by default, not something your provisioning code decided.\n\n"
        "Named appliance images do exist for clusters like this, and the recipe may come in\n"
        "several variants differing by site and accelerator, which is precisely why guessing\n"
        "is unsafe: naming CC-Ubuntu22.04, or any other appliance, as 'the image it boots'\n"
        "would be asserting something the code does not show. If you care which image you\n"
        "get, pass it explicitly rather than relying on a default.\n\n"
        "To see what the site offers:\n\n"
        "```python\n"
        "import chi\n"
        "from chi import hardware\n\n"
        'chi.use_site("CHI@UC")\n'
        "print(hardware.get_node_types())\n"
        "```\n"),
    gold_provenance=(
        "Restated standalone (deictic repair, second pass - missed by D86's determiner "
        "regex because 'multi-site' is hyphenated). Grounded in A43 not_covered, 'No image "
        "is passed as a call kwarg, although three named appliance images exist for this "
        "artifact', and A43 traps_illustrated, 'Four variants differ by site and accelerator'. "
        "Generalised to the property that makes it true: a kwarg never passed cannot be "
        "recovered from the call."),
    _anchor=["not passed", "does not show", "explicitly", "cannot tell", "default"],
)


def main() -> int:
    for item_id in sorted(set(FORBIDDEN)):
        path = ITEMS / f"{item_id}.yaml"
        d = yaml.safe_load(path.read_text(encoding="utf-8"))

        if item_id == "CB41":
            repair = dict(CB41)
            anchor = repair.pop("_anchor")
            d.update(repair)
            hits = [c for c in d["checkers"] if c.get("check") == "required_text_string"]
            if len(hits) != 1:
                raise SystemExit(f"{item_id}: expected 1 required_text_string checker")
            hits[0]["any"] = anchor
            for a in anchor:
                if a.lower() in d["prompt"].lower():
                    raise SystemExit(f"{item_id}: anchor {a!r} appears in its own prompt")
            d.pop("prompt_sha256", None)

        for c in d["checkers"]:
            if c.get("check") == "forbidden_calls":
                c["names"] = list(FORBIDDEN[item_id])
            elif c.get("check") == "abstain_or_discover":
                c["abstain_patterns"] = list(CHAMELEON_ABSTAIN)

        path.write_text(yaml.safe_dump(d, sort_keys=False, width=100,
                                       allow_unicode=True, default_flow_style=False),
                        encoding="utf-8")

    print(f"repaired {len(FORBIDDEN)} abstention items "
          f"(forbidden_calls narrowed, abstain_patterns added; CB41 restated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
