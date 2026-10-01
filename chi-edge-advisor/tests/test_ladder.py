"""The selection ladder: capability, site, live state, and honest refusals.

Every guard here has been mutation-tested: broken deliberately, confirmed to
turn a test red, restored.
"""
import unittest
from datetime import datetime, timedelta, timezone

from advisor.availability.base import DeviceAvailability
from advisor.inventory.catalog import DeviceType
from advisor.select.ladder import (FUTURE_HORIZON_HOURS, MAX_EXPANSIONS,
                                   Request, _hours_until, meets, select)


def dt(name, *, site="CHI@TACC", accel="none", ram=128, vcpus=48,
       cc=None, tensor=0, cores=0, covered=()):
    return DeviceType(machine_type=name, architecture="x86_64",
                      gpu=accel in {"cuda", "rocm", "oneapi"}, accelerator=accel,
                      sites=[site], api_family="baremetal", node_count=4,
                      ram_gb=ram, vcpus=vcpus, cuda_compute=cc,
                      tensor_cores=tensor, cuda_cores=cores,
                      covered_by=list(covered))


def hosts(mtype, *, site="CHI@TACC", free=0, busy=0, unknown=0, down=0,
          free_in=None):
    """Availability rows. free_in is hours until each busy host frees."""
    out, i = [], 0
    def add(**kw):
        nonlocal i
        i += 1
        out.append(DeviceAvailability(device_uid=f"{mtype}-uid-{i}",
                                      device_name=f"{mtype}-{i:02d}",
                                      machine_type=mtype, site=site, **kw))
    for _ in range(free):
        add(free_now=True, reservable=True)
    when = None
    if free_in is not None:
        when = (datetime.now(timezone.utc)
                + timedelta(hours=free_in)).isoformat()
    for _ in range(busy):
        add(free_now=False, reservable=True, next_free_window=when)
    for _ in range(unknown):
        add(free_now=None, reservable=True)
    for _ in range(down):
        add(free_now=True, reservable=False)
    return out


class TestCapabilityFilter(unittest.TestCase):
    def test_null_ram_fails_a_minimum(self):
        """R4. An absent measurement is not a measurement of absence."""
        self.assertIsNotNone(meets(dt("x", ram=None), {"min_ram_gb": 64}))
        self.assertIsNone(meets(dt("x", ram=128), {"min_ram_gb": 64}))

    def test_null_vcpus_and_cuda_compute_fail_too(self):
        self.assertIsNotNone(meets(dt("x", vcpus=None), {"min_vcpus": 8}))
        self.assertIsNotNone(
            meets(dt("x", accel="cuda", cc=None), {"min_cuda_compute": 7.0}))

    def test_rocm_is_not_cuda(self):
        """The wing's central trap: an MI100 is often the best free GPU."""
        mi100 = dt("gpu_mi100", accel="rocm")
        self.assertIsNotNone(meets(mi100, {"accelerator": "cuda"}))
        self.assertIsNone(meets(mi100, {"accelerator": "rocm"}))
        self.assertIsNone(meets(mi100, {"accelerator": ["cuda", "rocm"]}))

    def test_capability_refusal_is_not_an_availability_refusal(self):
        cat = [dt("compute_cpu", accel="none")]
        r = select(cat, hosts("compute_cpu", free=9),
                   Request(site="CHI@TACC", requires={"accelerator": "cuda"}))
        self.assertEqual(r.rung.name, "infeasible_capability")
        self.assertIsNone(r.chosen)
        # Nine free hosts, and still no. Waiting cannot fix this.
        self.assertEqual(r.ranked, [])
        self.assertEqual(r.rejected[0].machine_type, "compute_cpu")
        self.assertIn("accelerator", r.rejected[0].reject_reason)


class TestSiteFilter(unittest.TestCase):
    def test_hardware_at_another_site_is_never_offered(self):
        """R6. gpu_rtx_6000 is CHI@UC only."""
        cat = [dt("gpu_rtx_6000", site="CHI@UC", accel="cuda", cc=7.5)]
        r = select(cat, hosts("gpu_rtx_6000", site="CHI@UC", free=5),
                   Request(site="CHI@TACC", requires={"accelerator": "cuda"}))
        self.assertEqual(r.rung.name, "infeasible_capability")
        self.assertIsNone(r.chosen)

    def test_free_hosts_at_another_site_do_not_count(self):
        cat = [dt("shared", site="CHI@TACC")]
        # Plenty free, all of them somewhere else.
        r = select(cat, hosts("shared", site="CHI@UC", free=9),
                   Request(site="CHI@TACC"))
        self.assertIsNone(r.chosen)
        self.assertEqual(r.ranked[0].free, 0)
        # And the verdict is "we have no CHI@TACC state", not "CHI@TACC is
        # busy": nine free hosts somewhere else are not evidence about here.
        self.assertEqual(r.rung.name, "unknown_availability")
        self.assertFalse(r.ranked[0].state_known)


class TestFreeNowRung(unittest.TestCase):
    def test_picks_the_first_free_candidate(self):
        cat = [dt("a"), dt("b")]
        r = select(cat, hosts("a", free=3) + hosts("b", free=1),
                   Request(site="CHI@TACC", count=1))
        self.assertEqual(r.rung.name, "free_now")
        self.assertEqual(r.rung.expansions, 0)
        self.assertEqual(r.chosen.machine_type, "a")

    def test_names_a_specific_free_host(self):
        r = select([dt("a")], hosts("a", free=2), Request(site="CHI@TACC"))
        self.assertEqual(r.chosen.example_host, "a-01")

    def test_count_is_respected(self):
        cat = [dt("small"), dt("big")]
        r = select(cat, hosts("small", free=2) + hosts("big", free=5),
                   Request(site="CHI@TACC", count=4))
        self.assertEqual(r.chosen.machine_type, "big")

    def test_unknown_is_not_free(self):
        """R5. A node we cannot see is not a node we can have."""
        r = select([dt("a")], hosts("a", unknown=8), Request(site="CHI@TACC"))
        self.assertNotEqual(r.rung.name, "free_now")
        self.assertEqual(r.ranked[0].free, 0)
        self.assertEqual(r.ranked[0].unknown, 8)

    def test_unreservable_is_not_free(self):
        # free_now=True but reservable=False: maintenance. Offering it yields
        # a spec that cannot be submitted.
        r = select([dt("a")], hosts("a", down=8), Request(site="CHI@TACC"))
        self.assertNotEqual(r.rung.name, "free_now")
        self.assertEqual(r.ranked[0].free, 0)


class TestFutureRung(unittest.TestCase):
    def test_reports_the_wait(self):
        r = select([dt("a")], hosts("a", busy=3, free_in=6.0),
                   Request(site="CHI@TACC", count=1))
        self.assertEqual(r.rung.name, "future")
        self.assertAlmostEqual(r.rung.wait_hours, 6.0, places=1)

    def test_beyond_the_horizon_is_a_refusal(self):
        r = select([dt("a")],
                   hosts("a", busy=3, free_in=FUTURE_HORIZON_HOURS + 5),
                   Request(site="CHI@TACC"))
        self.assertEqual(r.rung.name, "infeasible_busy")
        self.assertIsNone(r.chosen)

    def test_future_rung_respects_count(self):
        """Two free and one freeing later does not answer a 3-node request now.

        This was a real defect: the free-now rung correctly rejected a type
        with 2 free against count=3, and the future rung then offered the same
        type without re-checking the count at all.
        """
        r = select([dt("a")], hosts("a", free=2) + hosts("a", busy=1, free_in=9.0),
                   Request(site="CHI@TACC", count=3))
        self.assertEqual(r.rung.name, "future")
        self.assertAlmostEqual(r.rung.wait_hours, 9.0, places=1)

    def test_wait_is_for_the_nth_host_not_the_first(self):
        """Needing three more hosts means waiting for the third, not the first.

        Staggered on purpose: with only one host outstanding the correct
        answer and the off-by-one both read waits[0], and the bug survives.
        """
        av = (hosts("a", busy=1, free_in=2.0)
              + hosts("a", busy=1, free_in=5.0)
              + hosts("a", busy=1, free_in=9.0))
        r = select([dt("a")], av, Request(site="CHI@TACC", count=3))
        self.assertEqual(r.rung.name, "future")
        self.assertAlmostEqual(r.rung.wait_hours, 9.0, places=1)
        # And for a single node it is the soonest, not the last.
        r1 = select([dt("a")], av, Request(site="CHI@TACC", count=1))
        self.assertAlmostEqual(r1.rung.wait_hours, 2.0, places=1)

    def test_never_enough_hosts_is_a_refusal_not_a_wait(self):
        # Only 2 hosts exist; a 3-node request can never be met by this type.
        r = select([dt("a")], hosts("a", free=1) + hosts("a", busy=1, free_in=2.0),
                   Request(site="CHI@TACC", count=3))
        self.assertEqual(r.rung.name, "infeasible_busy")

    def test_past_timestamp_is_unknown_not_immediate(self):
        """A closed window on a busy host is not evidence it is free.

        Clamping a past instant to 0.0 hours turns data that says "busy" into
        the most optimistic possible reading.
        """
        stale = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        self.assertIsNone(_hours_until(stale))
        r = select([dt("a")],
                   [DeviceAvailability(device_uid="u", device_name="a-01",
                                       machine_type="a", site="CHI@TACC",
                                       free_now=False, reservable=True,
                                       next_free_window=stale)],
                   Request(site="CHI@TACC"))
        self.assertEqual(r.rung.name, "infeasible_busy")

    def test_unparseable_timestamp_is_unknown(self):
        self.assertIsNone(_hours_until("not-a-date"))
        self.assertIsNone(_hours_until(None))


class TestExpansion(unittest.TestCase):
    def test_free_now_never_needs_to_expand(self):
        """Ranking free-count-first makes the free-now rung reach in one pass.

        Not a weakness of the expansion rung, a property of the order: any
        type with enough free hosts sorts above every busy one, so if such a
        type exists at all it is already in the first window. Widening the
        list is what the FUTURE rung needs, and only that rung - recorded here
        so nobody later "fixes" an expansion count that is correctly zero.
        """
        cat = [dt(f"busy{i}", ram=256) for i in range(3)] + [dt("free_one", ram=8)]
        av = []
        for i in range(3):
            av += hosts(f"busy{i}", busy=2)
        av += hosts("free_one", free=2)
        r = select(cat, av, Request(site="CHI@TACC", count=1))
        self.assertEqual(r.rung.name, "free_now")
        self.assertEqual(r.chosen.machine_type, "free_one")
        self.assertEqual(r.rung.expansions, 0)

    def test_future_rung_widens_to_reach_a_sooner_wait(self):
        # All busy, so capability decides the order. The three most capable
        # will not free up for a week; the fourth is back in two hours.
        cat = [dt(f"slow{i}", ram=256 - i) for i in range(3)] + [dt("soon", ram=8)]
        av = []
        for i in range(3):
            av += hosts(f"slow{i}", busy=2, free_in=24 * 7)
        av += hosts("soon", busy=2, free_in=2.0)
        r = select(cat, av, Request(site="CHI@TACC", count=1))
        self.assertEqual(r.rung.name, "future")
        self.assertEqual(r.chosen.machine_type, "soon")
        self.assertGreater(r.rung.expansions, 0)
        self.assertAlmostEqual(r.rung.wait_hours, 2.0, places=1)

    def test_expansion_is_bounded_and_says_so(self):
        cat = [dt(f"t{i:02d}", ram=256 - i) for i in range(40)]
        av = []
        for i in range(40):
            av += hosts(f"t{i:02d}", busy=2)
        r = select(cat, av, Request(site="CHI@TACC"))
        self.assertEqual(r.rung.name, "infeasible_busy")
        self.assertLessEqual(r.rung.expansions, MAX_EXPANSIONS)
        self.assertIn("expansions", r.rung.detail)


class TestRefusalsAreDistinct(unittest.TestCase):
    def test_busy_refusal_keeps_the_qualifying_types(self):
        """"Everything suitable is busy" is not "nothing can do this".

        The first is an availability limit and the hardware is listed; the
        second is a capability limit and there is nothing to list.
        """
        r = select([dt("a"), dt("b")], hosts("a", busy=2) + hosts("b", busy=2),
                   Request(site="CHI@TACC"))
        self.assertEqual(r.rung.name, "infeasible_busy")
        self.assertIsNone(r.chosen)
        self.assertEqual({c.machine_type for c in r.ranked}, {"a", "b"})
        self.assertEqual(r.rejected, [])

    def test_never_silently_returns_the_last_candidate(self):
        r = select([dt("a")], hosts("a", busy=4), Request(site="CHI@TACC"))
        self.assertIsNone(r.chosen)
        self.assertFalse(r.rung.satisfied)


class TestKvm(unittest.TestCase):
    def test_kvm_makes_no_host_availability_claim(self):
        """KVM reserves flavors. Blazar's KVM hosts are hypervisor classes."""
        flavor = dt("m1.large", site="KVM@TACC")
        flavor.api_family = "kvm"
        r = select([flavor], [], Request(site="KVM@TACC", api_family="kvm"))
        self.assertEqual(r.rung.name, "no_host_state")
        self.assertTrue(r.rung.satisfied)
        self.assertEqual(r.chosen.machine_type, "m1.large")
        self.assertIn("flavors", r.rung.detail)


class TestProvenance(unittest.TestCase):
    def test_artifact_coverage_is_reported_not_required(self):
        """18 of 29 types are named by no artifact and must stay selectable."""
        cat = [dt("uncovered", ram=256), dt("covered", ram=8, covered=["A12"])]
        r = select(cat, hosts("uncovered", free=2) + hosts("covered", free=1),
                   Request(site="CHI@TACC"))
        self.assertEqual(r.chosen.machine_type, "uncovered")
        self.assertFalse(r.chosen.grounded)
        self.assertTrue(
            next(c for c in r.ranked if c.machine_type == "covered").grounded)


if __name__ == "__main__":
    unittest.main()


class TestUnknownAvailability(unittest.TestCase):
    """"We could not look" is not "everything is taken"."""

    def test_no_availability_data_is_not_a_busy_verdict(self):
        r = select([dt("a"), dt("b")], [], Request(site="CHI@TACC"))
        self.assertEqual(r.rung.name, "unknown_availability")
        self.assertIsNone(r.chosen)
        self.assertEqual({c.machine_type for c in r.ranked}, {"a", "b"})
        self.assertIn("unknown, not no", r.rung.detail)

    def test_partial_data_is_still_a_real_verdict(self):
        # One type reports in; the answer is about the site, not the gap.
        r = select([dt("a"), dt("b")], hosts("a", busy=2), Request(site="CHI@TACC"))
        self.assertEqual(r.rung.name, "infeasible_busy")

    def test_incapable_everywhere_still_beats_unknown(self):
        # A capability refusal does not depend on live state at all, so it
        # must not be downgraded to "we could not look".
        r = select([dt("cpu", accel="none")], [],
                   Request(site="CHI@TACC", requires={"accelerator": "cuda"}))
        self.assertEqual(r.rung.name, "infeasible_capability")


class TestStateKnownIsNotNodeCount(unittest.TestCase):
    def test_static_node_count_does_not_masquerade_as_live_state(self):
        """`total` falls back to the capability table when nothing reported.

        So `total == 0` can never detect "the backend said nothing", and a
        check written that way silently never fires - which is worse than not
        having it, because the refusal then claims certainty it lacks.
        """
        cat = [dt("a")]
        self.assertEqual(cat[0].node_count, 4)      # static count is non-zero
        r = select(cat, [], Request(site="CHI@TACC"))
        self.assertFalse(r.ranked[0].state_known)
        self.assertGreater(r.ranked[0].total, 0)    # from the table, not live
        self.assertEqual(r.rung.name, "unknown_availability")

    def test_reported_type_is_state_known_even_at_zero_free(self):
        r = select([dt("a")], hosts("a", busy=3), Request(site="CHI@TACC"))
        self.assertTrue(r.ranked[0].state_known)
        self.assertEqual(r.ranked[0].free, 0)


class TestPinnedClock(unittest.TestCase):
    """`now` is an input, not the wall clock.

    Blazar reports WHEN a host next frees, so a wait is a subtraction, and
    against a snapshot recorded at a fixed instant the thing subtracted must be
    that instant. Read against the wall clock, every wait in a pinned snapshot
    shrinks by a day each day and the 24h horizon separating `future` from
    `infeasible_busy` is crossed by the calendar rather than by the data.
    """

    def setUp(self):
        self.recorded = datetime(2026, 9, 4, 19, 52, 51, tzinfo=timezone.utc)
        self.frees_at = self.recorded + timedelta(hours=5)
        self.avail = [DeviceAvailability(
            device_uid="u1", device_name="n-01", machine_type="a",
            site="CHI@TACC", free_now=False, reservable=True,
            next_free_window=self.frees_at.isoformat())]
        self.cat = [dt("a")]

    def _select(self, now):
        return select(self.cat, self.avail, Request(site="CHI@TACC", now=now))

    def test_the_wait_is_measured_from_the_given_instant(self):
        r = self._select(self.recorded)
        self.assertEqual(r.rung.name, "future")
        self.assertAlmostEqual(r.rung.wait_hours, 5.0, places=3)

    def test_the_same_snapshot_gives_the_same_answer_at_any_real_time(self):
        """The property the wall clock did not have."""
        a = self._select(self.recorded).rung.wait_hours
        b = self._select(self.recorded).rung.wait_hours
        self.assertEqual(a, b)
        # A year later, reading the same snapshot, the wait is still 5 hours.
        self.assertAlmostEqual(a, 5.0, places=3)

    def test_the_horizon_is_crossed_by_the_instant_supplied(self):
        """`now` must reach the rung comparison, not only the displayed wait.

        Asserted as a PAIR. The first version of this test checked only that a
        far-enough-back instant produced infeasible_busy, and passed under a
        mutation that ignored `now` entirely: with the wall clock the host had
        already freed in the past, which reaches the same rung by a different
        route. Two instants over one snapshot must give two different rungs,
        and nothing that ignores them can do that."""
        near = self._select(self.recorded)
        far = self._select(self.recorded - timedelta(hours=FUTURE_HORIZON_HOURS + 10))
        self.assertEqual(near.rung.name, "future")
        self.assertEqual(far.rung.name, "infeasible_busy")
        self.assertNotEqual(near.rung.name, far.rung.name)

    def test_none_still_means_the_wall_clock(self):
        """Live probes must be unaffected: a host freeing an hour from now is
        still an hour away when no instant is supplied."""
        soon = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        avail = [DeviceAvailability(
            device_uid="u1", device_name="n-01", machine_type="a",
            site="CHI@TACC", free_now=False, reservable=True,
            next_free_window=soon)]
        r = select(self.cat, avail, Request(site="CHI@TACC"))
        self.assertEqual(r.rung.name, "future")
        self.assertLess(r.rung.wait_hours, 1.1)
