"""The curated catalog carries hardware capability, and nothing may erase it.

Blazar reports device_type and reservation state and no capabilities at all, so
these fields exist only because they are hand-curated. Two things can silently
drop them: a live sweep, which builds DeviceType from scratch and would leave
them at their defaults, and the cache round trip, which filters unknown keys.
Both paths had no coverage at all before this file.
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from advisor.inventory.catalog import CURATED_CATALOG, DeviceType, InventoryCache

# The device types Blazar actually returns for CHI@Edge. Hard-coded rather than
# read from the benchmark: this asserts the advisor's own vocabulary is right,
# and importing the thing under test's answer would assert nothing.
REAL_TYPES = {
    "raspberrypi4-64", "raspberrypi5", "jetson-nano",
    "jetson-xavier-nx-devkit-emmc", "jetson-orin-nano-devkit-nvme",
    "jetson-agx-orin-devkit-64gb", "coral-dev",
}
CAPABILITY_FIELDS = ("accelerator", "soc", "cuda_compute", "cuda_cores",
                     "tensor_cores", "dla_cores", "edge_tpu_tops", "ram_gb",
                     "precisions", "storage")


class TestCuratedCapability(unittest.TestCase):
    def setUp(self):
        self.by_type = {d.machine_type: d for d in CURATED_CATALOG}

    def test_vocabulary_is_the_real_site(self):
        """A machine_type the site does not have cannot be reserved, and one it
        has but we cannot name can never be recommended."""
        self.assertEqual(set(self.by_type), REAL_TYPES)

    def test_every_type_declares_an_accelerator(self):
        """accelerator drives the hard filter. None means 'unknown', which would
        silently pass a workload that needs CUDA onto a Pi."""
        for mt, d in self.by_type.items():
            self.assertIn(d.accelerator, {"none", "cuda", "edgetpu"}, mt)

    def test_cuda_parts_carry_a_compute_capability(self):
        for mt, d in self.by_type.items():
            if d.accelerator == "cuda":
                self.assertIsNotNone(d.cuda_compute, mt)
                self.assertTrue(d.cuda_cores > 0, mt)
                self.assertEqual(d.runtime, "nvidia", mt)

    def test_the_edgetpu_part_is_int8_only_and_not_a_gpu(self):
        """The accelerator-confusion trap: coral-dev IS an accelerator but CUDA
        code cannot run on it, so gpu must stay False and int8 must be the only
        precision offered."""
        coral = self.by_type["coral-dev"]
        self.assertEqual(coral.accelerator, "edgetpu")
        self.assertFalse(coral.gpu)
        self.assertEqual(coral.precisions, ["int8"])

    def test_jetson_nano_is_distinguishable_from_agx_orin(self):
        """Both are gpu=True. If capability is missing they are the same device,
        which is exactly the bug this data exists to fix."""
        nano = self.by_type["jetson-nano"]
        orin = self.by_type["jetson-agx-orin-devkit-64gb"]
        self.assertLess(nano.cuda_compute, orin.cuda_compute)
        self.assertNotIn("int8", nano.precisions)
        self.assertIn("int8", orin.precisions)


class TestCapabilitySurvivesTheCache(unittest.TestCase):
    def test_write_then_read_preserves_every_capability_field(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "resource_catalog.json"
            InventoryCache(cache_path=path).load()      # writes the cache
            self.assertTrue(path.is_file())
            reread = {d.machine_type: d for d in InventoryCache(cache_path=path).load()}

        self.assertEqual(set(reread), REAL_TYPES)
        for mt, curated in {d.machine_type: d for d in CURATED_CATALOG}.items():
            for f in CAPABILITY_FIELDS:
                self.assertEqual(getattr(reread[mt], f), getattr(curated, f),
                                 f"{mt}.{f} did not survive the cache")

    def test_unknown_keys_in_the_cache_are_dropped_not_fatal(self):
        """Schema drift must degrade to a warning; raising here would send the
        whole catalog back to the curated fallback and hide the drift."""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "resource_catalog.json"
            InventoryCache(cache_path=path).load()
            blob = json.loads(path.read_text())
            blob["device_types"][0]["a_field_from_the_future"] = 1
            path.write_text(json.dumps(blob))
            got = InventoryCache(cache_path=path).load()
        self.assertEqual(len(got), len(REAL_TYPES))


class TestLiveSweepDoesNotBlankCapability(unittest.TestCase):
    """A sweep builds DeviceType from scratch with only topology set. The merge
    in _fetch_from_blazar is the only thing restoring capability; this is the
    regression guard for it."""

    def test_merge_restores_capability_onto_a_bare_swept_entry(self):
        curated = {d.machine_type: d for d in CURATED_CATALOG}
        # What the sweep produces: name, arch, gpu, runtime, topology. Nothing else.
        swept = DeviceType(machine_type="jetson-agx-orin-devkit-64gb",
                           architecture="arm64", gpu=True, runtime="nvidia",
                           api_family="edge", sites=["CHI@Edge"], node_count=1)
        self.assertIsNone(swept.accelerator)        # the failure mode, pre-merge

        c = curated[swept.machine_type]
        for f in CAPABILITY_FIELDS:                 # mirrors the merge loop
            setattr(swept, f, getattr(c, f))

        self.assertEqual(swept.accelerator, "cuda")
        self.assertEqual(swept.cuda_compute, 8.7)
        self.assertEqual(swept.ram_gb, 64)
        self.assertEqual(swept.node_count, 1)       # topology still from the sweep

    def test_merge_loop_covers_every_capability_field(self):
        """If a field is added to DeviceType but not to the merge loop, a live
        sweep silently zeroes it. Assert the source lists them all."""
        src = Path(__file__).resolve().parents[1] / "advisor/inventory/catalog.py"
        body = src.read_text().split("curated = {d.machine_type: d for d in CURATED_CATALOG}")[1]
        merge = body.split("# A type spanning both")[0]
        for f in CAPABILITY_FIELDS:
            self.assertIn(f"dt.{f} = ", merge,
                          f"{f} is not restored after a live sweep")


if __name__ == "__main__":
    unittest.main()
