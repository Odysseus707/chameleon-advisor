"""RouterTree tests: site gate, use-case routing, flat-parity (offline embedder)."""
import unittest

from advisor.artifacts.embeddings import HashingEmbedder
from advisor.artifacts.router import RetrievalRouter
from advisor.artifacts.store import ArtifactStore
from advisor.artifacts.registry import EDGE_ARTIFACTS
from advisor.artifacts.tree import RouterTree, WorkloadSpec


class TreeTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deterministic, offline: hashing embedder over the real grounding docs.
        cls.store = ArtifactStore(embedder=HashingEmbedder()).build()
        # The flat router is scoped to the edge pool. Unscoped it now competes
        # 95 artifacts for every query, which is a different operation.
        cls.flat = RetrievalRouter(
            cls.store, artifacts=[a.artifact_id for a in EDGE_ARTIFACTS])
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

    def test_populated_kvm_branch_now_routes(self):
        # Was "unpopulated site needs clarification". KVM@TACC has 26 grounded
        # artifacts since the registry became a loader, so the branch it used
        # to prove empty is the branch this phase existed to fill.
        spec = WorkloadSpec(
            text="boot a vm instance from a flavor with kvm virtualization",
            site="KVM@TACC",
        )
        r = self.tree.route(spec)
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.site, "KVM@TACC")
        self.assertTrue(r.selected_artifact_ids)

    def test_unpopulated_site_needs_clarification(self):
        # The guard still has to work; it just needs a genuinely empty branch
        # now, so the tree is built over the edge artifacts alone.
        tree = RouterTree(self.store, artifacts=EDGE_ARTIFACTS)
        spec = WorkloadSpec(
            text="boot a vm instance from a flavor with kvm virtualization",
            site="KVM@TACC",
        )
        r = tree.route(spec)
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
        # A bare string is never gated: no declaration means nothing to
        # disagree with. It now reaches the branch it actually describes,
        # which it could not do while KVM@TACC was empty.
        r = self.tree.route("boot a vm instance from a flavor with kvm virtualization")
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.site, "KVM@TACC")


class TestFlatParity(TreeTestBase):
    WORKLOADS = [
        "capture a photo and record video with the pi camera",
        "read temperature humidity and pressure from a sensor",
        "ssh into an edge device for an interactive shell",
        "run a machine learning image classification model",
        "camera sensor ssh inference everything at once",
        "xyzzy plugh nothing relevant here",  # all-zero fallback path
    ]

    def test_edge_branch_is_closed(self):
        """The CHI@Edge branch is exactly the five frozen artifacts.

        This is the R1 guard. Two corpus artifacts observe CHI@Edge, and
        letting them in drops measured edge L2 retrieval from 93.5% to 77.4%
        on the benchmark's own items - a regression against 3231 collected
        answer cells, wearing the costume of a bigger registry.
        """
        self.assertEqual(
            [m.artifact_id for m in self.tree.branches["CHI@Edge"]],
            [a.artifact_id for a in EDGE_ARTIFACTS],
        )

    def test_byte_identical_single_branch(self):
        # An edge workload routed through the tree must land on exactly what
        # the flat router over the edge pool produces: same selection, same
        # budget, same chunks, same assembled context. Widening the registry
        # is only additive if this keeps holding.
        for w in self.WORKLOADS:
            with self.subTest(workload=w):
                f = self.flat.route(w)
                # The site is declared. In a one-branch world it did not need
                # to be; with four branches an undeclared workload is entitled
                # to route somewhere else, and asserting otherwise would be
                # asserting that site routing does not work.
                t = self.tree.route(WorkloadSpec(text=w, site="CHI@Edge"))
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


class TestUnsitedAmbiguity(TreeTestBase):
    """A workload that names no site is routed on descriptor similarity alone.

    Recorded rather than papered over. On the benchmark's own items this is
    good enough - L0 is 134/134 on the edge suite and 32/32 on the chameleon
    suite, because real prompts say where they want to run. But similarity at
    these margins is noise, and a peripheral workload that mentions neither a
    site nor an edge device can land on the wrong branch by 0.007.
    """

    # Item P28 of the edge suite. Chosen because the embedding gets it WRONG:
    # the prompt is dense with CHI@UC vocabulary and scores CHI@UC 0.409 over
    # CHI@Edge 0.280, so a test that did not actually depend on reading the
    # name would pass here by luck. Blinding _named_site must break this.
    PORTING = ("Convert my CHI@UC bare-metal script (add_node_reservation, "
               "node_type='compute_skylake', create_server) to run on CHI@Edge.")

    def test_embedding_alone_gets_the_porting_prompt_wrong(self):
        # Pins the premise of the test below: without the name, this misroutes.
        scores = self.tree._site_scores(self.PORTING)
        self.assertEqual(max(scores, key=scores.get), "CHI@UC")

    def test_last_named_site_wins(self):
        # A porting request names its source first and its destination last;
        # the destination is the site the user wants code for.
        self.assertEqual(self.tree._named_site(self.PORTING), "CHI@Edge")
        self.assertEqual(self.tree.route(self.PORTING).site, "CHI@Edge")

    def test_unsited_workload_falls_back_to_similarity(self):
        # No name to read, so the descriptors decide - and on this workload
        # they are wrong by 0.007. Recorded, not hidden.
        text = "read temperature humidity and pressure from a sensor"
        self.assertIsNone(self.tree._named_site(text))
        self.assertEqual(self.tree.route(text).status, "ok")


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
