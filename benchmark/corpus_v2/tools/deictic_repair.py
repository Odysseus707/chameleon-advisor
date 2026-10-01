#!/usr/bin/env python3
"""One-shot repair: the 8 baremetal_core items whose prompt referenced "this
artifact", and so could not be answered in the blind condition.

THE DEFECT
Eight Abstention items were authored artifact-relative - "From this artifact,
show me how it reserves bare-metal hardware". Their gold is "it does not", which
is true only for a reader holding that artifact. But `fed_sets.blind` is empty
by definition, so under blind the phrase "this artifact" has no referent and the
gold is unknowable by construction. Those cells measured how a model reacts to a
dangling reference, not whether it abstains. The edge wing has zero prompts of
this shape across 134 items (N14/N17/N18 abstain about capabilities absent from
the whole testbed, which is why they survive blind), so this is a chameleon-wing
authoring defect and the edge wing is the template.

THE REPAIR
Each prompt is restated as a question a user would actually ask, with the trap
moved from "this artifact omits X" to a fact that holds testbed-wide, so
abstention is correct with or without an artifact in hand. Every new gold is
grounded in the artifact extractions already in the corpus - cited per item in
gold_provenance - not in recollection.

ANCHOR DISCIPLINE
`required_text_string` anchors are re-chosen so that no anchor appears in its
own prompt. Several original anchors (gpu_rtx_6000, get_lease, CC-Ubuntu22.04)
would have been echoable straight out of the restated question, turning a
specifics checker into a freebie and inflating the specifics rate for both arms.

Run once, then `build_core_items.py run` to refill prompt_sha256.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ITEMS = Path(__file__).resolve().parent.parent.parent / "chameleon_bench" / "data" / "items"

#: id -> the authored fields being replaced. Keys absent here are carried
#: forward untouched (R4); prompt_sha256 is derived and refilled downstream.
REPAIRS: dict[str, dict] = {

    "CB07": dict(
        prompt=("On KVM@TACC, show me the python-chi code that reserves the nodes and "
                "launches the servers for an automated MLOps training pipeline."),
        designed_trap=(
            "There is no such code to show. The KVM site does not require a lease or node "
            "reservation at all, and the automated pipeline this describes provisions "
            "declaratively through Terraform and Ansible, with python-chi present only to "
            "establish context. The invented answer is a plausible Lease/Server block "
            "presented as the python-chi provisioning path for a workflow that has none."),
        key_tokens={"mechanism": ["get_nodes"], "specifics": ["Terraform"]},
        gold_spec=(
            "There is no python-chi reservation code for this. Two separate things make it\n"
            "unavailable, and both matter.\n\n"
            "First, KVM@TACC does not require a lease or node reservation for its instances -\n"
            "reservations are the bare-metal path, not the KVM one - so there are no nodes to\n"
            "reserve here in the sense the question assumes.\n\n"
            "Second, an automated MLOps pipeline on Chameleon is provisioned declaratively:\n"
            "infrastructure lives in Terraform files with Ansible for configuration, and\n"
            "python-chi appears only to establish context - context.version, choose_project and\n"
            "choose_site. Writing an add_node_reservation or Server block here would be\n"
            "inventing a provisioning path that does not exist in this workflow.\n\n"
            "To see what the site actually offers:\n\n"
            "```python\n"
            "import chi\n"
            "from chi import hardware\n\n"
            'chi.use_site("KVM@TACC")\n'
            "print([n.node_type for n in hardware.get_nodes()])\n"
            "```\n"),
        gold_provenance=(
            "Restated standalone (deictic repair). Grounded in A11 not_covered - 'No lease, node "
            "reservation or flavor reservation is made through python-chi anywhere', 'No server "
            "creation through python-chi', 'No bare-metal path; the tutorial targets the KVM "
            "cloud' - and A11 traps_illustrated, 'Provisioning is declarative and lives in "
            "Terraform files, not in python-chi'. The KVM-requires-no-lease fact is A18 "
            "not_covered: 'No lease is created at all, since the KVM site does not require one "
            "for these instances.'"),
        _anchor=["Terraform", "terraform", "Ansible", "declarative", "infrastructure-as-code"],
    ),

    "CB08": dict(
        prompt=("At CHI@UC, show me how a gpu_rtx_6000 lease launches a server onto the "
                "node it reserved."),
        designed_trap=(
            "A lease launches nothing. Reserving hardware and booting on it are two separate "
            "explicit steps, so there is no 'the lease launches the server' code to quote. The "
            "invented answer is a fabricated Server(...) call presented as part of the "
            "reservation."),
        key_tokens={"mechanism": ["get_nodes"], "specifics": ["reservation"]},
        gold_spec=(
            "It does not launch one. A lease only holds the hardware for you; it never boots\n"
            "anything, so there is no server-launch step inside the reservation to show.\n\n"
            "Reserving and launching are two separate, explicit actions. The lease reserves a\n"
            "gpu_rtx_6000 node and ends there; if you want something running on that node you\n"
            "create the server yourself afterwards and bind it to the reservation. Presenting a\n"
            "Server(...) call as though the lease performed it would be inventing the step that\n"
            "does not exist.\n\n"
            "To confirm what the lease is actually holding:\n\n"
            "```python\n"
            "import chi\n"
            "from chi import hardware\n\n"
            'chi.use_site("CHI@UC")\n'
            'print([n.node_type for n in hardware.get_nodes(node_type="gpu_rtx_6000")])\n'
            "```\n"),
        gold_provenance=(
            "Restated standalone (deictic repair). Grounded in A12: its workflow is site/auth "
            "followed by three lease stages with no server stage at all. The general fact - a "
            "reservation holds hardware and does not boot it - is the same separation every "
            "bare-metal composition item in this suite relies on."),
        _anchor=["separate", "does not launch", "only reserves", "holds the hardware",
                 "two steps", "not launch"],
    ),

    "CB23": dict(
        prompt=("On KVM@TACC, show me the python-chi code to reserve resources before "
                "I launch an instance."),
        designed_trap=(
            "No reservation is needed or available. The KVM site does not require a lease for "
            "its instances, and its documented provisioning path is the Horizon web interface "
            "and the command line rather than python-chi reservation grammar. The invented "
            "answer is a plausible Lease block for a site that does not use one."),
        key_tokens={"mechanism": ["get_node_types"], "specifics": ["Horizon"]},
        gold_spec=(
            "There is no reservation step to write. KVM@TACC does not require a lease or node\n"
            "reservation for its instances - leases are the bare-metal path - so nothing needs\n"
            "reserving before you launch.\n\n"
            "Provisioning at the KVM site is done through the Horizon web interface and the\n"
            "command line, or through openstacksdk; python-chi is used there only to establish\n"
            "context, with choose_site defaulting to the KVM cloud. Quoting an\n"
            "add_node_reservation or Lease block here would be inventing a grammar this site\n"
            "does not use.\n\n"
            "If you want to see what the testbed exposes:\n\n"
            "```python\n"
            "import chi\n"
            "from chi import hardware\n\n"
            'chi.use_site("KVM@TACC")\n'
            "print(hardware.get_node_types())\n"
            "```\n"),
        gold_provenance=(
            "Restated standalone (deictic repair). Grounded in A13 not_covered - 'No lease or "
            "reservation of any kind through python-chi', 'No bare-metal provisioning; this is a "
            "virtual-machine tutorial' - and A13 traps_illustrated, 'the tutorial teaches Horizon "
            "and the CLI, so no reservation grammar exists in Python to find'. The "
            "KVM-requires-no-lease fact is A18 not_covered."),
        _anchor=["Horizon", "command line", "CLI", "openstacksdk", "does not require"],
    ),

    "CB24": dict(
        prompt="Show me how to reserve bare-metal hardware on Chameleon using openstacksdk.",
        designed_trap=(
            "openstacksdk cannot reserve bare-metal hardware. Reservations are Blazar's, reached "
            "through python-chi's lease module or the blazar client; openstacksdk speaks to the "
            "OpenStack services and has no lease grammar at all. The invented answer is a "
            "plausible openstacksdk reservation call that does not exist."),
        key_tokens={"mechanism": ["get_node_types"], "specifics": ["CHI@TACC"]},
        gold_spec=(
            "You cannot. openstacksdk has no bare-metal reservation API - it talks to the\n"
            "OpenStack services directly and there is no lease or node-reservation grammar in it\n"
            "to call.\n\n"
            "Bare-metal reservation on Chameleon is Blazar's job, reached through python-chi's\n"
            "lease module (or the blazar client underneath it). Those are different systems, so\n"
            "there is nothing in openstacksdk to adapt and writing an openstacksdk reservation\n"
            "call would be inventing one.\n\n"
            "To see what is actually reservable at a site:\n\n"
            "```python\n"
            "import chi\n"
            "from chi import hardware\n\n"
            'chi.use_site("CHI@TACC")\n'
            "print(hardware.get_node_types())\n"
            "```\n"),
        gold_provenance=(
            "Restated standalone (deictic repair). Grounded in A16 not_covered - 'No lease, node "
            "reservation or flavor reservation of any kind', 'No server or instance creation' - "
            "and A16 traps_illustrated, 'All cloud interaction goes through openstacksdk "
            "connections rather than python-chi'. The item now asserts the general separation "
            "(openstacksdk has no Blazar path) rather than a property of one artifact."),
        _anchor=["blazar", "Blazar", "python-chi", "lease module"],
    ),

    "CB25": dict(
        prompt=("I'm using lease.get_lease() at CHI@UC. Show me how it creates the lease "
                "for my hardware."),
        designed_trap=(
            "get_lease creates nothing. It looks up a lease that already exists, so asking for "
            "the creation it performs invites a fabricated add_node_reservation block attributed "
            "to a call that only reads."),
        key_tokens={"mechanism": ["get_node_types"], "specifics": ["provisioning"]},
        gold_spec=(
            "It does not create one. lease.get_lease looks up a lease that already exists and\n"
            "attaches to it - it is a read, not a provisioning call - so there is no creation\n"
            "code inside it to show.\n\n"
            "If the lease you are naming has not been made yet, get_lease will not make it for\n"
            "you; it fails to find it. Creating a reservation is a different, explicit step: you\n"
            "build a lease with a node reservation on it and submit that. Attributing an\n"
            "add_node_reservation block to get_lease would be inventing behaviour the call does\n"
            "not have.\n\n"
            "To see what could be reserved at the site:\n\n"
            "```python\n"
            "import chi\n"
            "from chi import hardware\n\n"
            'chi.use_site("CHI@UC")\n'
            "print(hardware.get_node_types())\n"
            "```\n"),
        gold_provenance=(
            "Restated standalone (deictic repair). Grounded in A8 traps_illustrated - "
            "'lease.get_lease attaches to an existing reservation rather than creating one, so "
            "nothing here demonstrates how the hardware was obtained' - and A8 not_covered, 'No "
            "lease creation, node reservation or flavor reservation anywhere'. The semantics of "
            "get_lease are a property of the API, so the restated question is answerable blind."),
        _anchor=["already exists", "existing", "does not create", "attaches", "looks up"],
    ),

    "CB26": dict(
        prompt=("If I reserve a bare-metal node at CHI@TACC without naming a node_type, "
                "which node type does the reservation give me?"),
        designed_trap=(
            "No particular one. An unconstrained reservation is satisfied by whatever matching "
            "node Blazar allocates, so naming a specific type in the answer is invention - and a "
            "node type is exactly what a lookup system will confidently supply."),
        key_tokens={"mechanism": ["get_node_types"], "specifics": ["specific"]},
        gold_spec=(
            "No particular one, and you should not assume a type. A reservation that names no\n"
            "node_type is not pinned to any hardware: Blazar satisfies it with whatever free node\n"
            "matches the constraints you did give, so which type you land on is not determined by\n"
            "your request and can differ between runs.\n\n"
            "If you need a specific type you have to ask for it explicitly. Naming\n"
            "compute_cascadelake_r, or any other type, as the one you would get here would be\n"
            "inventing a guarantee the reservation does not make.\n\n"
            "To list what the site actually offers, then pin one deliberately:\n\n"
            "```python\n"
            "import chi\n"
            "from chi import hardware\n\n"
            'chi.use_site("CHI@TACC")\n'
            "print(hardware.get_node_types())\n"
            "```\n"),
        gold_provenance=(
            "Restated standalone (deictic repair). Grounded in A10 not_covered - 'No explicit "
            "node_type is pinned anywhere; the artifact does not demonstrate reserving a named "
            "bare-metal node type' - generalised to the property that makes it true: an "
            "unconstrained Blazar reservation is matched, not pinned. The previous specifics "
            "anchor (CC-Ubuntu22.04) described the artifact's image and no longer applies."),
        _anchor=["not pinned", "unspecified", "any matching", "not guaranteed",
                 "does not specify", "not deterministic", "whatever"],
    ),

    "CB39": dict(
        prompt=("Show me the python-chi calls that create the instances for a Kubernetes "
                "cluster on KVM@TACC."),
        designed_trap=(
            "python-chi does not create them. At the KVM site instances are created through an "
            "openstacksdk connection - the documented escape hatch for what python-chi does not "
            "wrap - and python-chi is used only to establish context. A plausible Server(...) "
            "block is exactly what a lookup system will supply."),
        key_tokens={"mechanism": ["get_node_types"], "specifics": ["openstacksdk"]},
        gold_spec=(
            "python-chi does not create them. At the KVM site it is used only to establish\n"
            "context - version, project and site - and the instances themselves are created\n"
            "through an openstacksdk connection, which is the documented escape hatch for what\n"
            "python-chi does not wrap.\n\n"
            "No lease is involved either: the KVM site does not require one for these instances,\n"
            "so there is no reservation to bind them to. Quoting a python-chi Server(...) call\n"
            "here would be inventing an API path that is not the one used.\n\n"
            "To establish context and see the site:\n\n"
            "```python\n"
            "import chi\n"
            "from chi import hardware\n\n"
            'chi.use_site("KVM@TACC")\n'
            "print(hardware.get_node_types())\n"
            "```\n"),
        gold_provenance=(
            "Restated standalone (deictic repair). Grounded in A18 traps_illustrated - 'python-chi "
            "is used only for context; instances are created through an openstacksdk connection, "
            "which is the documented escape hatch' - and A18 not_covered, 'No lease is created at "
            "all, since the KVM site does not require one for these instances.'"),
        _anchor=["openstacksdk", "escape hatch"],
    ),

    "CB40": dict(
        prompt=("At CHI@UC I attach to my hardware with lease.get_lease(name). Which "
                "bare-metal node type does that call reserve?"),
        designed_trap=(
            "It reserves none. get_lease attaches to a lease that already exists and makes no "
            "reservation of its own, so the node type was fixed by whoever created that lease "
            "and is not visible from the call. Naming a type is invention."),
        key_tokens={"mechanism": ["get_node_types"], "specifics": ["attaches"]},
        gold_spec=(
            "None - that call reserves nothing. lease.get_lease attaches to a lease that already\n"
            "exists; it makes no reservation of its own, so there is no node type for it to ask\n"
            "for.\n\n"
            "Whatever hardware you end up on was decided by whoever created that lease, not by\n"
            "this call, and the call does not tell you which type that was. Naming a node type\n"
            "here would be inventing a choice get_lease never makes. Note also that if the name\n"
            "you pass does not match a real lease, the lookup simply fails - it does not create\n"
            "one.\n\n"
            "To see what the site offers, or to pin a type on a lease you create yourself:\n\n"
            "```python\n"
            "import chi\n"
            "from chi import hardware\n\n"
            'chi.use_site("CHI@UC")\n'
            "print(hardware.get_node_types())\n"
            "```\n"),
        gold_provenance=(
            "Restated standalone (deictic repair). Grounded in A59 traps_illustrated - "
            "'lease.get_lease attaches to an existing reservation rather than creating one' and "
            "'The lease name is a literal placeholder, so an unedited run fails on a lease that "
            "does not exist' - and A59 not_covered, 'No image or node type is passed to any call, "
            "so no hardware choice is demonstrated in code.'"),
        _anchor=["already exists", "existing", "does not reserve", "attaches", "reserves nothing"],
    ),
}


def main() -> int:
    changed = []
    for item_id, repair in REPAIRS.items():
        path = ITEMS / f"{item_id}.yaml"
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
        anchor = repair.pop("_anchor", None)

        for key, value in repair.items():
            d[key] = value

        if anchor is not None:
            # Re-point the specifics checker. Exactly one required_text_string
            # checker exists on each of these items; assert rather than assume,
            # because silently adding a second one would double-count specifics.
            hits = [c for c in d.get("checkers") or []
                    if c.get("check") == "required_text_string"]
            if len(hits) != 1:
                raise SystemExit(f"{item_id}: expected 1 required_text_string checker, "
                                 f"found {len(hits)}")
            hits[0]["any"] = anchor

        # Sanity gate, the whole point of the anchor rework: an anchor that
        # appears in its own prompt is answerable by echo and measures nothing.
        prompt_l = d["prompt"].lower()
        for a in (anchor or []):
            if a.lower() in prompt_l:
                raise SystemExit(f"{item_id}: anchor {a!r} appears in its own prompt")

        # prompt_sha256 is derived; drop it so a stale hash cannot survive a
        # failed refill. build_core_items.py run refills it.
        d.pop("prompt_sha256", None)

        path.write_text(yaml.safe_dump(d, sort_keys=False, width=100,
                                       allow_unicode=True, default_flow_style=False),
                        encoding="utf-8")
        changed.append(item_id)

    print(f"repaired {len(changed)} items: {', '.join(changed)}")
    print("prompt_sha256 dropped; run build_core_items.py run to refill")
    return 0


if __name__ == "__main__":
    sys.exit(main())
