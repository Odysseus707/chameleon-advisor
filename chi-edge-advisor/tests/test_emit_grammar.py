"""Emitted specs, graded by the benchmark's OWN checkers.

This is the strongest test available and it is nearly free: the same
`chi_edge_bench.harness.checks` functions that grade every collected answer are
run against the advisor's output. If the advisor and the benchmark ever
disagree about what valid python-chi looks like, it fails here rather than in a
score nobody can explain.
"""
import sys
import unittest
from pathlib import Path

from advisor.emit.spec import dry_check, render_spec
from advisor.reason.schema import Recommendation

_BENCH = Path(__file__).resolve().parents[2] / "benchmark"
if _BENCH.is_dir() and str(_BENCH) not in sys.path:
    sys.path.insert(0, str(_BENCH))

try:
    from chi_edge_bench.harness.checks import run_checks
except ImportError:      # pragma: no cover
    run_checks = None


def rec(family, mtype, **kw):
    base = dict(machine_type=mtype, count=1, duration_hours=4,
                architecture="x86_64", image="CC-Ubuntu24.04", reasoning="",
                api_family=family, produced_by="ladder")
    base.update(kw)
    return Recommendation(**base)


BAREMETAL = rec("baremetal", "compute_haswell_ib", site="CHI@TACC")
NAMED = rec("baremetal", "compute_haswell_ib", site="CHI@TACC",
            device_name="c01-22", selection_rung="free_now")
KVM = rec("kvm", "m1.large", site="KVM@TACC")


@unittest.skipIf(run_checks is None, "chi-edge-bench not importable")
class TestAgainstBenchmarkCheckers(unittest.TestCase):
    def _run(self, r, specs):
        code = render_spec(r)
        results = run_checks(code, code, specs)
        for res in results:
            self.assertTrue(res["passed"], f"{res['check']}: {res['detail']}\n{code}")
        return results

    def test_baremetal_passes_the_baremetal_grammar(self):
        self._run(BAREMETAL, [
            {"check": "server_call"},
            {"check": "node_reservation_wiring"},
            {"check": "site_correct", "site": "CHI@TACC"},
            # name_no_underscore is deliberately absent: it is a
            # CHI@Edge/Kubernetes rule and it requires a container-creation
            # call, which bare metal does not have.
            {"check": "lease_hours", "hours": 4},
            {"check": "required_call", "name": "add_node_reservation"},
            # The edge grammar on a bare-metal site is the classic wrong answer.
            {"check": "forbidden_calls",
             "names": ["add_device_reservation", "Container", "create_container"]},
        ])

    def test_named_host_still_passes(self):
        self._run(NAMED, [
            {"check": "server_call"},
            {"check": "node_reservation_wiring"},
            {"check": "site_correct", "site": "CHI@TACC"},
        ])

    def test_kvm_passes_the_flavor_grammar(self):
        """The check the old emitter could not have passed.

        It wired reservation_id (the bare-metal spelling) and called
        add_flavor_reservation with a flavor_name kwarg that does not exist.
        """
        self._run(KVM, [
            {"check": "server_call"},
            {"check": "flavor_reservation_wiring"},
            {"check": "site_correct", "site": "KVM@TACC"},
            {"check": "forbidden_calls",
             "names": ["add_node_reservation", "add_device_reservation"]},
        ])

    def test_edge_grammar_is_untouched(self):
        r = rec("edge", "raspberrypi4-64", site="CHI@Edge",
                image="ghcr.io/chameleoncloud/edge_ssh_image:latest")
        code = render_spec(r)
        results = run_checks(code, code, [
            {"check": "container_call"},
            {"check": "reservation_wiring"},
            {"check": "site_correct", "site": "CHI@Edge"},
            {"check": "forbidden_calls",
             "names": ["add_node_reservation", "create_server"]},
        ])
        for res in results:
            self.assertTrue(res["passed"], f"{res['check']}: {res['detail']}")


class TestBrokenIdiomsAreNeverEmitted(unittest.TestCase):
    def test_get_node_reservation_never_appears(self):
        """F3: deprecated AND broken in python-chi 1.2.10.

        _reservation_matching expects a lease dict while get_lease returns a
        Lease object, so it raises AttributeError. It appears in A9, A55, A61,
        A63 and A77 - the corpus actively teaches an idiom that cannot run.
        """
        for r in (BAREMETAL, NAMED, KVM):
            self.assertNotIn("get_node_reservation", render_spec(r))

    def test_kvm_never_emits_the_nonexistent_flavor_name_kwarg(self):
        code = render_spec(KVM)
        self.assertNotIn("add_flavor_reservation(amount", code)
        self.assertIn("get_reserved_flavors", code)
        # reservation_id is the bare-metal spelling and does not belong here.
        self.assertNotIn("reservation_id", code)


class TestNamedHostTargeting(unittest.TestCase):
    def test_named_host_is_primary_with_a_commented_type_fallback(self):
        code = render_spec(NAMED)
        self.assertIn('node_name="c01-22"', code)
        self.assertIn('# my_lease.add_node_reservation(amount=1, '
                      'node_type="compute_haswell_ib")', code)

    def test_the_race_is_stated_not_hidden(self):
        self.assertIn("fails if someone else takes it first", render_spec(NAMED))

    def test_no_named_host_means_a_plain_type_request(self):
        code = render_spec(BAREMETAL)
        self.assertIn('node_type="compute_haswell_ib"', code)
        self.assertNotIn("node_name=", code)


class TestDryCheck(unittest.TestCase):
    def test_non_edge_is_no_longer_excused(self):
        for r in (BAREMETAL, KVM):
            c = dry_check(r)
            self.assertTrue(c.passed, c.details)
            self.assertEqual(c.mode, "ast")
            self.assertFalse(any("structural validation only" in d
                                 for d in c.details))

    def test_literal_flavor_name_is_caught(self):
        from advisor.emit.spec import _audit_source
        bad = ('my_lease.add_flavor_reservation(id=1, amount=1)\n'
               'my_server = server.Server("x", flavor_name="m1.large")\n')
        out = _audit_source(bad, "kvm")
        self.assertTrue(any(d.startswith("FAIL") for d in out), out)

    def test_lease_id_where_reservation_id_belongs_is_caught(self):
        from advisor.emit.spec import _audit_source
        bad = ('my_lease.add_node_reservation(amount=1, node_type="t")\n'
               'my_server = server.Server(name="x", reservation_id=my_lease.id)\n')
        out = _audit_source(bad, "baremetal")
        self.assertTrue(any("not derived from the lease" in d for d in out), out)

    def test_broken_idiom_is_caught(self):
        from advisor.emit.spec import _audit_source
        bad = ('my_lease.add_node_reservation(amount=1, node_type="t")\n'
               'r = lease.get_node_reservation(my_lease)\n'
               'my_server = server.Server(name="x", '
               'reservation_id=my_lease.node_reservations[0]["id"])\n')
        out = _audit_source(bad, "baremetal")
        self.assertTrue(any("AttributeError" in d for d in out), out)


if __name__ == "__main__":
    unittest.main()
