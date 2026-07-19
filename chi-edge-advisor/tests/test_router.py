"""RetrievalRouter artifact-selection tests (offline hashing embedder)."""
import unittest

from advisor.artifacts.embeddings import HashingEmbedder
from advisor.artifacts.router import RetrievalRouter
from advisor.artifacts.store import ArtifactStore


class RouterTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deterministic, offline: hashing embedder over the real grounding docs.
        cls.store = ArtifactStore(embedder=HashingEmbedder()).build()
        cls.router = RetrievalRouter(cls.store)


class TestClassification(RouterTestBase):
    def test_camera_workload_selects_picamera(self):
        r = self.router.route("capture a photo and record video with the pi camera")
        self.assertEqual(r.selected_artifact_ids[0], "edge-picamera-image")
        self.assertIn("edge-picamera-image", r.provenance)

    def test_sensor_workload_selects_sensehat(self):
        r = self.router.route("read temperature humidity and pressure from a sensor")
        self.assertEqual(r.selected_artifact_ids[0], "edge_sensehat_image")

    def test_ssh_workload_selects_ssh(self):
        r = self.router.route("ssh into an edge device for an interactive shell")
        self.assertEqual(r.selected_artifact_ids[0], "edge_ssh_image")

    def test_inference_workload_selects_cpu_inference(self):
        r = self.router.route("run a machine learning image classification model")
        self.assertEqual(r.selected_artifact_ids[0], "edge-cpu-inference")


class TestBudgetAndProvenance(RouterTestBase):
    def test_budget_sums_to_total(self):
        r = self.router.route("camera photo and sensor temperature readings")
        self.assertEqual(sum(r.per_artifact_budget.values()), self.router.total_budget)

    def test_max_artifacts_respected(self):
        r = self.router.route("camera sensor ssh inference everything at once")
        self.assertLessEqual(len(r.selected_artifact_ids), self.router.max_artifacts)

    def test_provenance_only_contributing_artifacts(self):
        r = self.router.route("pi camera photo")
        self.assertTrue(set(r.provenance) <= set(r.selected_artifact_ids))
        self.assertTrue(r.provenance)

    def test_unmatched_workload_falls_back_to_best(self):
        r = self.router.route("xyzzy plugh nothing relevant here")
        # always yields at least one artifact so downstream has grounding
        self.assertTrue(r.selected_artifact_ids)


if __name__ == "__main__":
    unittest.main()
