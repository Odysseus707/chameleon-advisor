"""Capability tiers.

The whole point of this module is that an unmeasured node must not read as a
weak one. Every test below is a way that can go wrong.
"""
import unittest

from advisor.inventory.catalog import DeviceType, capability_table_types
from advisor.inventory.tiers import (CPU_GENERATION, Tier, partition,
                                     smallest_sufficient, tier_for)


def dev(name, *, accel="none", cc=None, micro="", ram=None, vcpus=None):
    return DeviceType(machine_type=name, architecture="x86_64",
                      gpu=accel in {"cuda", "rocm", "oneapi"}, accelerator=accel,
                      cuda_compute=cc, microarchitecture=micro,
                      ram_gb=ram, vcpus=vcpus, api_family="baremetal")


class TestNullsAreNotWeakness(unittest.TestCase):
    def test_unmeasured_type_is_unranked_not_worst(self):
        """The defect this module exists for.

        capability_score gives gpu_mi100 exactly 0 because Blazar reported no
        RAM and no vCPUs, and 0 sorts last. An MI100 is one of the most capable
        accelerators at CHI@TACC.
        """
        mi100 = tier_for(dev("gpu_mi100", accel="rocm", micro="AMD"))
        self.assertFalse(mi100.known)
        self.assertIn("cannot be ranked", mi100.describe())

    def test_unranked_types_are_kept_out_of_the_ordered_list(self):
        """Both ends of a sorted list are a lie for an unmeasured type."""
        tiers = [tier_for(d) for d in (
            dev("known_a", micro="Intel Haswell", ram=125, vcpus=24),
            dev("known_b", micro="Intel Ice Lake"),
            dev("unmeasured", micro="Intel"),
        )]
        ranked, unranked = partition(tiers)
        self.assertEqual([t.machine_type for t in unranked], ["unmeasured"])
        self.assertNotIn("unmeasured", [t.machine_type for t in ranked])

    def test_exceeds_is_none_when_we_cannot_tell(self):
        """None, not False. False would let "we cannot tell" read as "no"."""
        known = tier_for(dev("k", micro="Intel Skylake", ram=188, vcpus=48))
        blank = tier_for(dev("b", micro="Intel"))
        self.assertIsNone(blank.exceeds(known))
        self.assertIsNone(known.exceeds(blank))

    def test_missing_size_does_not_sink_a_named_generation(self):
        # compute_zen3 has a real microarchitecture and no measured size; it
        # must still outrank Haswell, which is older but fully measured.
        zen3 = tier_for(dev("compute_zen3", micro="AMD Zen 3"))
        haswell = tier_for(dev("compute_haswell_ib", micro="Intel Haswell",
                               ram=125, vcpus=24))
        self.assertTrue(zen3.known)
        self.assertTrue(zen3.exceeds(haswell))


class TestClassIsAKindNotARank(unittest.TestCase):
    def test_different_classes_are_incomparable(self):
        cuda = tier_for(dev("gpu_p100", accel="cuda", cc=6.0))
        rocm = tier_for(dev("gpu_mi100", accel="rocm", ram=256))
        self.assertFalse(cuda.comparable_to(rocm))
        self.assertIsNone(cuda.exceeds(rocm))
        self.assertIsNone(rocm.exceeds(cuda))

    def test_a_bigger_rocm_card_does_not_satisfy_a_cuda_need(self):
        """The wing's central trap, expressed as an ordering question.

        An MI100 with more of everything is still not a CUDA device, and no
        tier arithmetic may be allowed to suggest otherwise.
        """
        weak_cuda = tier_for(dev("gpu_k80", accel="cuda", cc=3.7,
                                 ram=125, vcpus=48))
        big_rocm = tier_for(dev("gpu_mi100", accel="rocm", ram=512, vcpus=128))
        self.assertIsNone(big_rocm.exceeds(weak_cuda))


class TestOrderingWithinAClass(unittest.TestCase):
    def test_cuda_orders_by_compute_capability(self):
        tiers = [tier_for(dev(n, accel="cuda", cc=cc)) for n, cc in
                 (("gpu_h100", 9.0), ("gpu_k80", 3.7), ("gpu_p100", 6.0))]
        ranked, _ = partition(tiers)
        self.assertEqual([t.machine_type for t in ranked],
                         ["gpu_k80", "gpu_p100", "gpu_h100"])

    def test_h100_exceeds_k80(self):
        h = tier_for(dev("gpu_h100", accel="cuda", cc=9.0))
        k = tier_for(dev("gpu_k80", accel="cuda", cc=3.7, ram=125, vcpus=48))
        self.assertTrue(h.exceeds(k))
        self.assertFalse(k.exceeds(h))

    def test_cpu_orders_by_generation_then_size(self):
        older = tier_for(dev("a", micro="Intel Haswell", ram=125, vcpus=24))
        newer = tier_for(dev("b", micro="Intel Cascade Lake", ram=188, vcpus=32))
        self.assertTrue(newer.exceeds(older))

    def test_same_generation_falls_through_to_size(self):
        small = tier_for(dev("a", micro="Intel Cascade Lake", ram=188, vcpus=32))
        large = tier_for(dev("b", micro="Intel Cascade Lake", ram=188, vcpus=48))
        self.assertTrue(large.exceeds(small))

    def test_bare_vendor_name_is_not_a_generation(self):
        """"Intel" appears on 8 types and names no generation."""
        self.assertNotIn("intel", CPU_GENERATION)
        t = tier_for(dev("compute_gigaio", micro="Intel"))
        self.assertIsNone(t.generation)
        self.assertFalse(t.known)


class TestSmallestSufficient(unittest.TestCase):
    def test_prefers_the_least_machine_that_clears_the_bar(self):
        """Slightly overpowered, not maximally overpowered.

        Reaching for the biggest free node is how one user takes an H100 to run
        a job a P100 would have finished.
        """
        tiers = [tier_for(dev(n, accel="cuda", cc=cc)) for n, cc in
                 (("gpu_h100", 9.0), ("gpu_p100", 6.0), ("gpu_v100", 7.0))]
        floor = tier_for(dev("floor", accel="cuda", cc=6.5))
        self.assertEqual(smallest_sufficient(tiers, floor).machine_type,
                         "gpu_v100")

    def test_no_floor_returns_the_smallest(self):
        tiers = [tier_for(dev(n, accel="cuda", cc=cc)) for n, cc in
                 (("gpu_h100", 9.0), ("gpu_p100", 6.0))]
        self.assertEqual(smallest_sufficient(tiers).machine_type, "gpu_p100")

    def test_all_unranked_returns_none_not_a_guess(self):
        tiers = [tier_for(dev("a", micro="Intel")),
                 tier_for(dev("b", micro="Intel"))]
        self.assertIsNone(smallest_sufficient(tiers))


class TestAgainstTheRealTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tiers = {t.machine_type: t for t in
                     (tier_for(d) for d in capability_table_types())}

    def test_every_cuda_type_has_a_generation(self):
        """cuda_compute is complete for all eleven, so CUDA needs no fallback.

        Eleven, not ten: compute_liqid joined when the reference API showed
        that all 8 of its nodes carry an A100 the table had recorded as no GPU
        at all. It is named for its composable fabric, not its accelerator,
        which is exactly why reading `accelerator` off the node_type name
        stopped being safe.
        """
        cuda = [t for t in self.tiers.values() if t.accel_class == "cuda"]
        self.assertEqual(len(cuda), 11)
        self.assertIn("compute_liqid", [t.machine_type for t in cuda])
        for t in cuda:
            self.assertIsNotNone(t.generation, t.machine_type)

    def test_nothing_is_unranked_now_that_every_type_is_measured(self):
        """The unranked bucket is empty, and that is a finding, not a bug.

        It used to hold seven types - gpu_mi100, gpu_pontevecchio, fpga,
        compute_gigaio, compute_liqid, compute_nvdimm, storage_nvme - because
        Blazar measured no size for them and their microarchitecture is a bare
        vendor name. The reference API measured all seven, so `known` is now
        true for every row. The MECHANISM is still tested, on a synthetic type,
        by test_an_unmeasured_type_is_still_unranked below: this assertion is
        about the data, that one is about the rule.
        """
        _, unranked = partition(self.tiers.values())
        self.assertEqual([t.machine_type for t in unranked], [])

    def test_an_unmeasured_type_is_still_unranked(self):
        """R4 at the ordering layer, independent of what the table happens to say.

        Sorting a type we know nothing about into the ranked list puts it at
        one end or the other and BOTH ends are a lie: at the front it reads as
        the weakest hardware on the testbed, at the back as the strongest.
        """
        blank = tier_for(dev("mystery", micro="Intel"))
        self.assertFalse(blank.known)
        ranked, unranked = partition([blank, *self.tiers.values()])
        self.assertEqual([t.machine_type for t in unranked], ["mystery"])
        self.assertNotIn("mystery", [t.machine_type for t in ranked])

    def test_h100_is_the_top_cuda_tier(self):
        cuda = [t for t in self.tiers.values() if t.accel_class == "cuda"]
        ranked, _ = partition(cuda)
        self.assertEqual(ranked[-1].machine_type, "gpu_h100")
        self.assertEqual(ranked[0].machine_type, "gpu_k80")


if __name__ == "__main__":
    unittest.main()
