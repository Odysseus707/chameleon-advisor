"""Bare-metal capability loading (chameleon wing).

The capability table is the only authority on what bare-metal hardware can do.
These tests guard the three ways that authority gets quietly corrupted: a null
turning into a zero, an accelerator turning into "GPU", and a cache handing one
wing's table to the other.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from advisor.inventory.catalog import (CURATED_CATALOG, DeviceType,
                                       InventoryCache, capability_table_types)


def _cache():
    return InventoryCache(cache_path=Path(tempfile.mkdtemp()) / "c.json")


def _offline():
    """Assert the static catalogue, not whatever the network answered.

    Without this the tests below pass or fail on whether CHI@Edge happened to
    be reachable, which is not what they are about. The sweep is neutralised
    rather than settings.offline flipped, because Settings is frozen and
    because an empty sweep is exactly the condition being described.
    """
    return mock.patch.object(InventoryCache, "_fetch_from_blazar",
                             lambda self: [])


class TestCapabilityTable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.types = capability_table_types()
        cls.by_name = {d.machine_type: d for d in cls.types}

    def test_all_29_load_as_baremetal(self):
        self.assertEqual(len(self.types), 29)
        for d in self.types:
            self.assertEqual(d.api_family, "baremetal")
            # kvm_compute is a CHI@TACC bare-metal node type despite the name.
            self.assertTrue(set(d.sites) <= {"CHI@UC", "CHI@TACC"}, d.machine_type)

    def test_null_measurements_stay_null(self):
        """R4. A null is not a zero, and must survive the loader as one.

        A null coerced to 0 still fails a `min_ram_gb` today, but it fails
        while claiming the node has no RAM, and it would pass any check
        written as "is this value known". The distinction has to survive the
        loader or it cannot be made downstream.

        This used to hold for 17 of 29 types, because Blazar reported
        `memory_mb` for only 102 of 345 TACC hosts. The reference-API refill
        measured 27 of them, so the guard now rests on compute_haswell - the
        one type BOTH sources are silent about, because it was decommissioned.
        The rule under test is unchanged; only how many rows exercise it.
        """
        nulls = [d for d in self.types if d.ram_gb is None]
        self.assertEqual([d.machine_type for d in nulls], ["compute_haswell"])
        for d in nulls:
            self.assertIsNone(d.ram_gb)
            self.assertIsNone(d.vcpus)
            self.assertIsNotNone(d.machine_type)
        # Explicitly not 0: the coercion this test exists to catch.
        self.assertNotEqual(self.by_name["compute_haswell"].ram_gb, 0)

    def test_vcpus_is_carried(self):
        # meets() filters on min_vcpus; without this field it never binds.
        self.assertEqual(self.by_name["gpu_rtx_6000"].vcpus, 24)

    def test_vcpus_is_one_unit_across_identical_hardware(self):
        """The defect the reference-API refill existed to remove.

        compute_haswell_ib, gpu_k80, gpu_m40, gpu_p100, gpu_p100_v100 and
        storage_hierarchy are all 2x Xeon E5-2670 v3 - 24 physical cores. The
        table used to say 24 for the first and 48 for the others, because
        Blazar's `vcpus` was whatever Ironic recorded per node rather than a
        unit. Any threshold tested against that column was comparing different
        quantities on different rows, silently.
        """
        same_silicon = ["compute_haswell_ib", "gpu_k80", "gpu_m40", "gpu_p100",
                        "gpu_p100_v100", "storage_hierarchy"]
        for name in same_silicon:
            self.assertEqual(self.by_name[name].vcpus, 24, name)
        # compute_skylake, fpga and gpu_rtx_6000 are all 2x Gold 6126.
        for name in ["compute_skylake", "fpga", "gpu_rtx_6000"]:
            self.assertEqual(self.by_name[name].vcpus, 24, name)

    def test_accelerator_is_verbatim_not_collapsed_to_cuda(self):
        """The wing's central trap. "GPU" means NVIDIA everywhere else."""
        self.assertEqual(self.by_name["gpu_mi100"].accelerator, "rocm")
        self.assertEqual(self.by_name["gpu_pontevecchio"].accelerator, "oneapi")
        self.assertEqual(self.by_name["fpga"].accelerator, "fpga")
        self.assertEqual(self.by_name["gpu_p100"].accelerator, "cuda")
        # An MI100 IS a GPU - the coarse flag must not be read as "runs CUDA".
        self.assertTrue(self.by_name["gpu_mi100"].gpu)
        self.assertNotEqual(self.by_name["gpu_mi100"].accelerator, "cuda")

    def test_site_membership_is_exact(self):
        """R6. Recommending hardware absent from the site is never fixable."""
        self.assertEqual(self.by_name["gpu_rtx_6000"].sites, ["CHI@UC"])
        self.assertEqual(self.by_name["gpu_mi100"].sites, ["CHI@TACC"])
        self.assertEqual(self.by_name["gpu_p100"].sites, ["CHI@TACC"])

    def test_no_container_runtime_on_bare_metal(self):
        # runtime="nvidia" is a CHI@Edge container concern; bare metal boots a
        # whole machine and has no container to configure.
        for d in self.types:
            self.assertIsNone(d.runtime, d.machine_type)

    def test_covered_by_is_provenance_only(self):
        """R3: capability never comes from an artifact.

        18 of 29 types are named by no artifact. If coverage fed capability
        they would be uniformly incapable, which they are not.
        """
        uncovered = [d for d in self.types if not d.covered_by]
        self.assertEqual(len(uncovered), 18)
        self.assertTrue(any(d.ram_gb is not None for d in uncovered))
        self.assertTrue(any(d.accelerator == "cuda" for d in uncovered))

    def test_cache_is_keyed_by_path(self):
        """P3: an unkeyed cache grades the second caller against the first."""
        missing = Path(tempfile.mkdtemp()) / "nope.yaml"
        self.assertEqual(capability_table_types(missing), [])
        # The real table must still load afterwards, not return the empty hit.
        self.assertEqual(len(capability_table_types()), 29)

    def test_callers_cannot_mutate_the_cached_table(self):
        first = capability_table_types()
        first[0].ram_gb = 999_999
        self.assertNotEqual(capability_table_types()[0].ram_gb, 999_999)


class TestMergedInventory(unittest.TestCase):
    def test_edge_and_baremetal_coexist(self):
        with _offline():
            inv = _cache().load()
        self.assertEqual(len(inv), len(CURATED_CATALOG) + 29)
        fams = {d.api_family for d in inv}
        self.assertEqual(fams, {"edge", "baremetal"})

    def test_edge_entries_are_unchanged(self):
        with _offline():
            by = {d.machine_type: d for d in _cache().load()}
        for c in CURATED_CATALOG:
            got = by[c.machine_type]
            self.assertEqual(got.accelerator, c.accelerator)
            self.assertEqual(got.node_count, c.node_count)
            self.assertEqual(got.device_profiles, c.device_profiles)
            self.assertEqual(got.api_family, "edge")

    def test_site_pruning_sees_baremetal(self):
        cache = _cache()
        with _offline():
            cache.load()
        self.assertEqual(cache.sites_for_types(["gpu_rtx_6000"]), ["CHI@UC"])
        self.assertEqual(cache.sites_for_types(["gpu_mi100"]), ["CHI@TACC"])
        self.assertEqual(
            cache.sites_for_types(["gpu_mi100", "raspberrypi4-64"]),
            ["CHI@Edge", "CHI@TACC"])

    def test_a_pre_baremetal_cache_is_treated_as_stale(self):
        """An old cache is not merely old, it is a different catalog.

        Staleness-by-age never notices: the file is perfectly fresh, it just
        describes a world with no bare metal in it. The symptom is an advisor
        answering "nothing at CHI@TACC can do this" while holding only edge
        hardware, which is how this was found.
        """
        import json
        from advisor.inventory.catalog import CATALOG_SCHEMA_VERSION
        path = Path(tempfile.mkdtemp()) / "c.json"
        with _offline():
            InventoryCache(cache_path=path).load()
            blob = json.loads(path.read_text())
            self.assertEqual(blob["schema_version"], CATALOG_SCHEMA_VERSION)
            blob["schema_version"] = CATALOG_SCHEMA_VERSION - 1
            blob["device_types"] = blob["device_types"][:2]
            path.write_text(json.dumps(blob))
            reloaded = InventoryCache(cache_path=path).load()
        self.assertGreater(len(reloaded), 2)

    def test_unknown_type_prunes_nothing(self):
        # Empty means "do not prune", not "no sites".
        cache = _cache()
        with _offline():
            cache.load()
        self.assertEqual(cache.sites_for_types(["no_such_type"]), [])


if __name__ == "__main__":
    unittest.main()
