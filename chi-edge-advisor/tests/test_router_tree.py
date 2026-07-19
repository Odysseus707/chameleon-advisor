"""RouterTree tests: site gate, use-case routing, flat-parity (offline embedder)."""
import unittest

from advisor.artifacts.embeddings import HashingEmbedder
from advisor.artifacts.router import RetrievalRouter
from advisor.artifacts.store import ArtifactStore
from advisor.artifacts.tree import RouterTree, WorkloadSpec


class TreeTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deterministic, offline: hashing embedder over the real grounding docs.
        cls.store = ArtifactStore(embedder=HashingEmbedder()).build()
        cls.flat = RetrievalRouter(cls.store)
        cls.tree = RouterTree(cls.store)


class TestSiteGate(TreeTestBase):
    def test_site_mismatch_needs_clarification(self):
        # Text reads like KVM@TACC but the spec declares CHI@Edge -> hard gate.
        spec = WorkloadSpec(
            text="boot a vm instance from a flavor with kvm virtualization",
            site="CHI@Edge",
        )
        r = self.tree.route(spec)
        self.assertEqual(r.status, "needs_clarification")
        self.assertIn("KVM@TACC", r.clarification)
        self.assertEqual(r.chunks, [])
        self.assertEqual(r.context_text, "")
        self.assertEqual(r.selected_artifact_ids, [])

    def test_unpopulated_site_needs_clarification(self):
        # Declaration and embedding agree on KVM@TACC, but no artifacts exist.
        spec = WorkloadSpec(
            text="boot a vm instance from a flavor with kvm virtualization",
            site="KVM@TACC",
        )
        r = self.tree.route(spec)
        self.assertEqual(r.status, "needs_clarification")
        self.assertIn("no grounded artifacts", r.clarification)

    def test_unknown_site_needs_clarification(self):
        spec = WorkloadSpec(text="pi camera photo", site="CHI@Mars")
        r = self.tree.route(spec)
        self.assertEqual(r.status, "needs_clarification")
        self.assertIn("unknown site", r.clarification)

    def test_site_agreement_passes(self):
        spec = WorkloadSpec(
            text="capture a photo with the pi camera on an edge device container",
            site="CHI@Edge",
        )
        r = self.tree.route(spec)
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.site, "CHI@Edge")
        self.assertTrue(r.chunks)

    def test_plain_string_never_gated(self):
        # Even KVM-leaning text routes to the only populated branch when the
        # workload is a bare string (spec.site is None).
        r = self.tree.route("boot a vm instance from a flavor with kvm virtualization")
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.site, "CHI@Edge")


class TestFlatParity(TreeTestBase):
    WORKLOADS = [
        "capture a photo and record video with the pi camera",
        "read temperature humidity and pressure from a sensor",
        "ssh into an edge device for an interactive shell",
        "run a machine learning image classification model",
        "camera sensor ssh inference everything at once",
        "xyzzy plugh nothing relevant here",  # all-zero fallback path
    ]

    def test_byte_identical_single_branch(self):
        # One populated branch + default knobs -> tree output must be
        # byte-identical to the flat router on the original surface.
        for w in self.WORKLOADS:
            with self.subTest(workload=w):
                f = self.flat.route(w)
                t = self.tree.route(w)
                self.assertEqual(t.status, "ok")
                self.assertEqual(f.task_scores, t.task_scores)
                self.assertEqual(f.selected_artifact_ids, t.selected_artifact_ids)
                self.assertEqual(f.per_artifact_budget, t.per_artifact_budget)
                self.assertEqual(f.provenance, t.provenance)
                self.assertEqual(f.context_text, t.context_text)
                self.assertEqual(
                    [(c.artifact_id, c.source_file, c.score, c.text) for c in f.chunks],
                    [(c.artifact_id, c.source_file, c.score, c.text) for c in t.chunks],
                )


class TestUseCaseRouting(TreeTestBase):
    def test_use_case_scores_are_group_max(self):
        r = self.tree.route("capture a photo with the pi camera")
        peripherals = max(
            r.task_scores["edge-picamera-image"], r.task_scores["edge_sensehat_image"]
        )
        self.assertEqual(r.use_case_scores["peripherals"], peripherals)
        self.assertEqual(r.use_case_scores["access"], r.task_scores["edge_ssh_image"])

    def test_use_case_topk_restricts_pool(self):
        tree = RouterTree(self.store, use_case_top_k=1)
        r = tree.route("camera photo and ssh shell login")
        self.assertEqual(r.status, "ok")
        self.assertEqual(len(r.selected_use_cases), 1)
        members = {
            uc: [m.artifact_id for m in tree.branches["CHI@Edge"] if m.use_case == uc]
            for uc in ("access", "peripherals", "inference")
        }
        allowed = set(members[r.selected_use_cases[0]])
        self.assertTrue(set(r.selected_artifact_ids) <= allowed)

    def test_budget_sums_to_total(self):
        r = self.tree.route("camera photo and sensor temperature readings")
        self.assertEqual(sum(r.per_artifact_budget.values()), self.tree.total_budget)

    def test_sections_align_with_chunks(self):
        r = self.tree.route("pi camera photo")
        self.assertEqual(len(r.sections), len(r.chunks))
        for i, (sec, chunk) in enumerate(zip(r.sections, r.chunks)):
            self.assertEqual(sec.index, i)
            self.assertEqual(sec.artifact_id, chunk.artifact_id)
            self.assertEqual(sec.source_file, chunk.source_file)
            self.assertEqual(sec.score, chunk.score)
            self.assertEqual(sec.site, "CHI@Edge")
            self.assertTrue(sec.use_case)


if __name__ == "__main__":
    unittest.main()
