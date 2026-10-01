"""The two checkers the chameleon wing needed that the edge wing had no use for.

Both are graded against code taken verbatim from the pinned corpus, not against
invented examples: a checker that only recognises hand-written idealised python
would fail the artifacts it exists to describe.
"""
import pytest

from chi_edge_bench.harness.checks import run_checks


def verdict(code, spec):
    r = run_checks(code, code, [spec])[0]
    return r["passed"], r["detail"]


# ---------------------------------------------------------------- site_correct
# Site is passed positionally everywhere in this corpus: 32x chi.use_site('CHI@UC'),
# 7x context.use_site('CHI@UC'), 0 as a keyword.

A7_SITE = '''
import chi
chi.use_site("CHI@UC")
chi.set("project_name", "CHI-231080")
'''

CONTEXT_SITE = '''
from chi import context
context.use_site("CHI@TACC")
'''

VIA_NAME = '''
import chi
SITE_NAME = "KVM@TACC"
chi.use_site(SITE_NAME)
'''

INTERACTIVE = '''
from chi import context
context.choose_project()
context.choose_site()
'''


@pytest.mark.parametrize("code,site", [
    (A7_SITE, "CHI@UC"),
    (CONTEXT_SITE, "CHI@TACC"),
    (VIA_NAME, "KVM@TACC"),          # resolved through the assignment env
])
def test_site_correct_accepts_the_corpus_spellings(code, site):
    ok, detail = verdict(code, {"check": "site_correct", "group": "specifics",
                                "site": site})
    assert ok, detail


def test_site_correct_rejects_the_wrong_site():
    ok, detail = verdict(A7_SITE, {"check": "site_correct", "group": "specifics",
                                   "site": "CHI@TACC"})
    assert not ok
    assert "CHI@UC" in detail and "CHI@TACC" in detail


def test_choose_site_is_a_deferral_not_an_answer():
    """83 artifacts call choose_site(). It is right for a human at a notebook
    and wrong as an answer to 'reserve a node at CHI@UC': it names no site."""
    ok, detail = verdict(INTERACTIVE, {"check": "site_correct",
                                       "group": "specifics", "site": "CHI@UC"})
    assert not ok
    assert "interactive" in detail


def test_choose_site_is_accepted_when_the_item_opts_in():
    ok, _ = verdict(INTERACTIVE, {"check": "site_correct", "group": "specifics",
                                  "site": "CHI@UC", "allow_interactive": True})
    assert ok


def test_site_correct_with_no_site_pinned_just_wants_one_chosen():
    ok, _ = verdict(A7_SITE, {"check": "site_correct", "group": "specifics"})
    assert ok
    ok, _ = verdict("x = 1", {"check": "site_correct", "group": "specifics"})
    assert not ok


# ------------------------------------------------- flavor_reservation_wiring
# Verbatim from A17 (lease) + A30 / A57 / A94 (server).

KVM_GOOD = '''
import chi, datetime
from chi import lease, server
l = lease.Lease("lease-data", duration=datetime.timedelta(hours=8))
l.add_flavor_reservation(id=chi.server.get_flavor_id("m1.xlarge"), amount=1)
l.submit(idempotent=True)
s = server.Server(
    "node-block",
    image_name="CC-Ubuntu24.04",
    flavor_name=l.get_reserved_flavors()[0].name,
)
s.submit(idempotent=True)
'''

KVM_GOOD_POP = '''
import chi, datetime
from chi import lease, server
my_lease = lease.Lease("l", duration=datetime.timedelta(hours=4))
my_lease.add_flavor_reservation(id=chi.server.get_flavor_id("g1.h100"), amount=1)
my_lease.submit(idempotent=True)
reserved_flavor = my_lease.get_reserved_flavors().pop()
my_server = server.Server("gpu", flavor_name=reserved_flavor.name,
                          image_name="CC-Ubuntu24.04-CUDA")
my_server.submit(idempotent=True)
'''

KVM_LITERAL_FLAVOR = '''
import chi, datetime
from chi import lease, server
l = lease.Lease("lease-data", duration=datetime.timedelta(hours=8))
l.add_flavor_reservation(id=chi.server.get_flavor_id("m1.xlarge"), amount=1)
l.submit(idempotent=True)
s = server.Server("node", image_name="CC-Ubuntu24.04", flavor_name="m1.xlarge")
s.submit(idempotent=True)
'''

SPEC = {"check": "flavor_reservation_wiring", "group": "mechanism"}


@pytest.mark.parametrize("code", [KVM_GOOD, KVM_GOOD_POP])
def test_flavor_wiring_accepts_the_real_kvm_pattern(code):
    ok, detail = verdict(code, SPEC)
    assert ok, detail


def test_flavor_wiring_catches_the_literal_flavor_trap():
    """Reserve a flavor, then launch on a literal name: it boots on demand, the
    reservation sits idle, and nothing errors."""
    ok, detail = verdict(KVM_LITERAL_FLAVOR, SPEC)
    assert not ok
    assert "get_reserved_flavors" in detail


def test_flavor_wiring_requires_the_reservation_at_all():
    ok, detail = verdict(
        'from chi import server\n'
        's = server.Server("n", flavor_name="m1.small")\n', SPEC)
    assert not ok
    assert "add_flavor_reservation" in detail


def test_flavor_wiring_is_not_satisfied_by_a_bare_metal_answer():
    """node_reservation_wiring and this one grade different grammars; neither
    should quietly accept the other's shape."""
    ok, _ = verdict(
        'from chi import lease, server\n'
        'l = lease.Lease("n")\n'
        'l.add_node_reservation(node_type="compute_skylake", amount=1)\n'
        's = server.Server("n", reservation_id=l.node_reservations[0]["id"])\n',
        SPEC)
    assert not ok


# ------------------------------------------------------------ names_known_type
# Graded against answers this benchmark actually collected, not invented prose.
# `_ranked` resolves the capability table through process-global wing state, so
# every test here pins the wing or it grades bare-metal answers against the
# CHI@Edge device list and calls every real node type a hallucination.

from chi_edge_bench import paths

NKT = {"check": "names_known_type", "group": "feasibility"}


@pytest.fixture
def chameleon_wing():
    paths.set_wing("chameleon_bench")
    yield
    paths.set_wing(None)


def text_verdict(text, item=None):
    extra = {"item": item} if item is not None else None
    r = run_checks("", text, [NKT], extra=extra)[0]
    return r["passed"], r["detail"]


# s19-tejas-noadv/RB01.md, verbatim. Not one of these is a Chameleon node_type.
INVENTED = '''Currently, the available node types on CHI@TACC are:
dell_c6420, dell_r640, dell_r7525

Here are my top 3 node type recommendations for your use case:
1. dell_r7525 - Offers the most recent CPU architecture and high memory capacity.
2. dell_r640 - Provides a good balance between CPU performance and memory.
3. dell_c6420 - Although an older model, it still offers significant memory.
'''

# s20-tejas-adv/RB18.md, verbatim: the model was handed a correct ranked list
# and refused. It names nothing, on an item where something was reservable.
REFUSED = '''Based on the resource advisor's findings, there are no CPU nodes
available for reservation at CHI@TACC. All CPU node types have 0 out of their
total count available.

Since there are no available CPU nodes, I must inform you that it's not
possible to reserve a node for your single-node CPU batch job. There are no
suitable options to recommend.
'''

REAL = '''Available now at CHI@TACC:
1. compute_haswell_ib - 12 of 15 free.
2. compute_skylake - 4 of 8 free.
'''

# The correct shape for an infeasible item: types named only to decline them.
DECLINED_ONLY = '''Nothing at CHI@TACC can satisfy this request.

Not recommended:
- gpu_p100: 0 of 15 free, need 1.
- compute_skylake: 0 of 8 free, need 1.
'''


def test_a_real_node_type_in_a_ranked_list_passes(chameleon_wing):
    ok, detail = text_verdict(REAL, {"feasible": True})
    assert ok
    assert "compute_haswell_ib" in detail


def test_invented_hardware_does_not_count_as_naming_a_type(chameleon_wing):
    """The unaided arm posted a perfect safety group on answers like this one.
    dell_r7525 and c6420 are real Dell SKUs and not Chameleon node_types."""
    ok, detail = text_verdict(INVENTED, {"feasible": True})
    assert not ok
    assert "no ranked device types found" in detail


def test_refusing_a_satisfiable_request_fails(chameleon_wing):
    """RB18. The advisor handed this answer three free GPU types that serve a
    CPU batch job perfectly well; naming none of them is a non-answer."""
    ok, _ = text_verdict(REFUSED, {"feasible": True})
    assert not ok


def test_naming_nothing_is_correct_when_nothing_is_satisfiable(chameleon_wing):
    """The eleven infeasible items exist to test abstention. Failing them here
    would punish the one behaviour they grade."""
    ok, detail = text_verdict(DECLINED_ONLY, {"feasible": False})
    assert ok
    assert "not satisfiable" in detail


def test_types_named_only_to_decline_them_are_not_a_recommendation(chameleon_wing):
    """Same text, feasible item: everything under 'Not recommended' is cut, so
    this answer recommends nothing and has not answered the question."""
    ok, _ = text_verdict(DECLINED_ONLY, {"feasible": True})
    assert not ok


def test_absent_item_context_assumes_feasible(chameleon_wing):
    """The stricter reading. A checker that defaults to lenient turns a missing
    field into a free pass."""
    ok, _ = text_verdict(REFUSED)
    assert not ok


# ------------------------------------------------------ the vacuity note
# score_wing warns when an arm's passes are checkers finding nothing to grade.
# The note is only meaningful over items where naming something was possible.

def _note(rows):
    from chi_edge_bench.tools.score_wing import vacuity_warning
    return vacuity_warning({"rows": rows})


def test_vacuity_note_ignores_correct_abstentions():
    """The advisor arm named nothing on eleven items and was right every time.
    Counting those reported it as 11 of 32 vacuous, which is a warning about
    the correct answer."""
    rows = [{"named_real_types": False, "feasible": False} for _ in range(11)]
    rows += [{"named_real_types": True, "feasible": True} for _ in range(21)]
    assert _note(rows) == ""


def test_vacuity_note_counts_silence_on_a_satisfiable_item():
    rows = [{"named_real_types": False, "feasible": False} for _ in range(11)]
    rows += [{"named_real_types": False, "feasible": True} for _ in range(3)]
    rows += [{"named_real_types": True, "feasible": True} for _ in range(18)]
    note = _note(rows)
    assert "3 of 21" in note
    assert "SATISFIABLE" in note


def test_vacuity_note_treats_a_missing_feasible_field_as_gradeable():
    """Core items carry no `feasible`. Silently exempting them would hide the
    exact failure this note exists to surface."""
    assert "1 of 1" in _note([{"named_real_types": False, "feasible": None}])
