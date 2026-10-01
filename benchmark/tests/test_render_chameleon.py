"""What the advisor's finding SAYS, not just what it concluded.

Nothing asserted on this text before. The ladder was covered, the checkers were
covered, and the string that carries the ladder's answer to a reader - and to
the model in the assisted arm - was covered by nothing at all. Two of the three
findings that motivated this file were rendering defects sitting inside a
correct recommendation.

Every guard here has been mutation-tested: broken deliberately, confirmed to
turn a test red, restored.
"""
import re

import pytest

from chi_edge_bench.harness.checks import _RANK_LINE, recommended_section
from chi_edge_bench.tools.run_advisor import render_chameleon

from advisor.availability.base import DeviceAvailability
from advisor.inventory.catalog import DeviceType
from advisor.select.ladder import Request, select


def dt(name, *, site="CHI@TACC", accel="none", ram=128, vcpus=48, api="baremetal"):
    d = DeviceType(machine_type=name, architecture="x86_64",
                   gpu=accel in {"cuda", "rocm"}, accelerator=accel,
                   sites=[site], api_family=api, node_count=4,
                   ram_gb=ram, vcpus=vcpus, covered_by=["A7"])
    return d


def hosts(mtype, *, site="CHI@TACC", free=0, busy=0):
    out = []
    for i in range(free):
        out.append(DeviceAvailability(device_uid=f"{mtype}-u{i}",
                                      device_name=f"{mtype}-{i:02d}",
                                      machine_type=mtype, site=site,
                                      free_now=True, reservable=True))
    for i in range(busy):
        out.append(DeviceAvailability(device_uid=f"{mtype}-b{i}",
                                      device_name=f"{mtype}-b{i:02d}",
                                      machine_type=mtype, site=site,
                                      free_now=False, reservable=True))
    return out


def ranked_lines(text):
    """What a checker would read as a recommendation, after the reject cut."""
    return _RANK_LINE.findall(recommended_section(text))


# ------------------------------------------------------------------- RB18
# A single-node CPU batch job on a snapshot where every CPU type is reserved.
# The ladder ranks the free GPU types, correctly: no accelerator was required.

# Three free GPU types, as in the real item: their reasons differ, so the
# per-type branch of the rendering is the one under test. With a single free
# type the shorter one-line branch runs instead and the loop is never executed
# - which is how the first version of these tests passed a mutation that
# emitted the reasons as bullets.
RB18_CATALOG = [dt("gpu_p100", accel="cuda", vcpus=48, ram=125),
                dt("gpu_mi100", accel="rocm", vcpus=64, ram=256),
                dt("compute_skylake", accel="none")]
RB18_AVAIL = (hosts("gpu_p100", free=15) + hosts("gpu_mi100", free=8)
              + hosts("compute_skylake", busy=32))


def render_rb18():
    r = select(RB18_CATALOG, RB18_AVAIL, Request(site="CHI@TACC", requires={}))
    return render_chameleon(r, "baremetal_tacc_inversion_2026-09-04", count=1)


def test_rb18_states_that_the_accelerator_is_incidental():
    """The item this phase exists for. The model was handed a correct ranked
    list of GPU types for a CPU job and answered 'there are no CPU nodes
    available'. The list was right; it just never said why."""
    out = render_rb18()
    assert "gpu_p100" in out
    assert "incidental" in out
    assert "48 vCPUs" in out


def test_rb18_still_ranks_the_gpu_first():
    """The explanation must not have cost the ranking."""
    assert ranked_lines(render_rb18())[0].startswith("gpu_p100")


def test_qualification_reason_is_not_itself_a_ranked_line():
    """The 'why' lines must not be read as extra recommendations: that is the
    same defect as F3, introduced by the fix for F1."""
    out = render_rb18()
    assert not any("incidental" in line for line in ranked_lines(out))


# --------------------------------------------------------------------- F3
# The rejected list was bullets, and the model copied the shape.

def test_rejected_types_are_not_rendered_as_a_list():
    """As '- {type}: {reason}' the model re-emitted them above its own
    rejection heading, where the rank-line pattern scored them as
    recommendations."""
    out = render_rb18()
    tail = out[out.index("Not recommended"):]
    assert "compute_skylake" in tail
    assert not _RANK_LINE.findall(tail), _RANK_LINE.findall(tail)


def test_rejected_types_are_still_named_and_still_explained():
    """Making it non-echoable must not make it uninformative."""
    out = render_rb18()
    assert "compute_skylake because 0 of 32 free" in out


# --------------------------------------------------------------------- KVM
def test_kvm_makes_no_host_availability_claim():
    """KVM reserves flavors, not hosts. This fell through to the free_now
    branch and printed 'Available now at KVM@TACC:' over a host tally that
    means nothing there."""
    flavor = dt("m1.large", site="KVM@TACC", api="kvm")
    r = select([flavor], [], Request(site="KVM@TACC", api_family="kvm"))
    out = render_chameleon(r, "kvm_tacc_2026-09-04")
    assert "Available now" not in out
    assert "flavors" in out
    assert "selection_rung=no_host_state" in out


# ------------------------------------------------- the requirement was stated
def test_a_stated_requirement_is_quoted_back_not_called_incidental():
    """The incidental clause is only correct when nothing was asked for. Saying
    it about a GPU the user explicitly required would be nonsense."""
    r = select([dt("gpu_p100", accel="cuda")], hosts("gpu_p100", free=8),
               Request(site="CHI@TACC", requires={"accelerator": "cuda"}))
    out = render_chameleon(r, "snap")
    assert "incidental" not in out
    assert "cuda accelerator" in out


def test_one_shared_reason_is_stated_once_not_repeated_per_type():
    """When every listed type qualifies for the same reason, saying it three
    times is noise. This is the other rendering branch."""
    r = select([dt("compute_skylake", accel="none")],
               hosts("compute_skylake", free=9),
               Request(site="CHI@TACC", requires={}))
    out = render_chameleon(r, "snap")
    assert out.count("Why these qualify") == 1
    assert "no hardware requirement was stated" in out


def test_none_is_a_value_in_the_accelerator_field_not_an_absence():
    """16 of the 29 bare-metal types carry the literal string "none". Testing
    truthiness rendered "its none is incidental" for every CPU type."""
    r = select([dt("compute_skylake", accel="none")],
               hosts("compute_skylake", free=9),
               Request(site="CHI@TACC", requires={}))
    out = render_chameleon(r, "snap")
    assert "none is incidental" not in out
    assert "its none" not in out
