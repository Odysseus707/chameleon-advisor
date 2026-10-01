"""run_advisor: the two wings must not contaminate each other.

The advisor's registry grew from 5 artifacts to 95 and its catalog from 7
device types to 36. Both changes are additive to the ADVISOR and both silently
moved the EDGE ARM's collected answers until each of the seams below was
scoped. Every assertion here corresponds to a diff that was actually observed
against runs/reservation/s17-advisor-busyhead.
"""
import ast
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "chi_edge_bench/tools/run_advisor.py"


def _tree():
    return ast.parse(SRC.read_text(encoding="utf-8"))


def _func(name):
    for node in ast.walk(_tree()):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() not found in {SRC.name}")


class TestEdgeArmStaysScoped(unittest.TestCase):
    def test_edge_router_is_given_an_artifact_pool(self):
        """Unscoped, all 95 artifacts compete for every edge query.

        Observed: R01 re-routed from edge-picamera-image to
        edge-cpu-inference and the emitted image changed with it. The
        recommendation for a published arm moved without a single test going
        red anywhere.
        """
        src = SRC.read_text(encoding="utf-8")
        self.assertIn("EDGE_ARTIFACTS", src)
        for node in ast.walk(_func("main")):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "RetrievalRouter"):
                kw = {k.arg for k in node.keywords}
                self.assertIn("artifacts", kw,
                              "the edge RetrievalRouter must be scoped to the "
                              "edge pool, or the whole registry competes")
                return
        self.fail("no RetrievalRouter construction found in main()")

    def test_edge_reasoner_gets_edge_inventory_only(self):
        """Unscoped, the reasoner rejects bare metal by name in an edge answer.

        Observed: R07 kept the same pick but its reasoning grew a rejection
        list running from compute_arm64 to storage_nvme, each "(no camera)",
        in an answer about a Raspberry Pi. The recommendation was unchanged;
        the graded text was not.
        """
        src = SRC.read_text(encoding="utf-8")
        self.assertIn('d.api_family == "edge"', src)
        for node in ast.walk(_func("main")):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "recommend"):
                names = [a.id for a in node.args if isinstance(a, ast.Name)]
                self.assertIn("edge_inventory", names,
                              "the edge reasoner must not be handed the "
                              "bare-metal catalog")
                self.assertNotIn("inventory", names)
                return
        self.fail("no reasoner.recommend call found in main()")


class TestWingIsSetExplicitly(unittest.TestCase):
    def test_main_calls_set_wing(self):
        """P2: the wing is process state.

        A run that forgets it resolves snapshots and the capability table to
        the edge wing and then grades bare-metal answers against CHI@Edge
        hardware. It is set for BOTH wings, including the default, because an
        implicit default is what makes the mistake invisible.
        """
        src = SRC.read_text(encoding="utf-8")
        self.assertIn("paths.set_wing(args.wing)", src)

    def test_capability_table_key_matches_the_wing(self):
        """The two tables do not share a top-level key.

        Bare metal is `node_types`; edge is `device_types`. Reading the wrong
        one is a KeyError at best and cross-wing grading at worst.
        """
        src = SRC.read_text(encoding="utf-8")
        self.assertIn('["node_types"]', src)
        self.assertIn('["device_types"]', src)


class TestSnapshotSchemasStaySeparate(unittest.TestCase):
    def test_chameleon_reader_uses_bare_metal_field_names(self):
        """Edge snapshots key uuid/device_type; bare metal uid/node_type."""
        src = ast.get_source_segment(SRC.read_text(encoding="utf-8"),
                                     _func("chameleon_availability"))
        self.assertIn('d["uid"]', src)
        self.assertIn('d["node_type"]', src)
        self.assertNotIn('d["uuid"]', src)
        self.assertNotIn('d["device_type"]', src)

    def test_chameleon_site_comes_from_the_item(self):
        """Hardcoding CHI@Edge makes the ladder's site filter reject every
        bare-metal candidate, turning every answer into a refusal."""
        src = ast.get_source_segment(SRC.read_text(encoding="utf-8"),
                                     _func("chameleon_availability"))
        self.assertIn('item["site"]', src)
        self.assertNotIn('"CHI@Edge"', src)


class TestVacuousRunsAreRefused(unittest.TestCase):
    def test_no_items_exits_nonzero(self):
        """P5: an empty result set reads as a pass.

        "0 items answered" with exit 0 is not a result an arm can be built on.
        """
        src = SRC.read_text(encoding="utf-8")
        self.assertIn("no items matched under", src)
        self.assertIn("return 0 if ok else 1", src)


if __name__ == "__main__":
    unittest.main()
