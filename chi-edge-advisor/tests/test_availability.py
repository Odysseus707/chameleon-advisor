"""Adapter interface tests (network mocked)."""
import unittest
from unittest import mock

from advisor.availability import DeviceAvailability, get_backend
from advisor.availability.base import AvailabilityBackend
from advisor.availability import reference_api
from advisor.http_util import HttpResult


def _fake_get_json(mapping):
    def _inner(url, timeout=None):
        for key, payload in mapping.items():
            if key in url:
                return HttpResult(url, 200, True, payload, None)
        return HttpResult(url, 404, False, None, "http 404")
    return _inner


class TestDeviceAvailability(unittest.TestCase):
    def test_defaults_mark_live_state_unknown(self):
        d = DeviceAvailability(device_uid="x", machine_type="raspberrypi4-64")
        self.assertIsNone(d.free_now)
        self.assertFalse(d.live_state_known)
        # unknown must not be reported as free unless explicitly opted in
        self.assertIsNone(d.is_free_in_window())
        self.assertTrue(d.is_free_in_window(unknown_ok=True))


class TestReferenceApiBackend(unittest.TestCase):
    def test_conforms_to_interface(self):
        self.assertIsInstance(reference_api.ReferenceApiBackend(), AvailabilityBackend)

    def test_lists_devices_from_clusters_nodes(self):
        mapping = {
            "clusters.json": {"items": [{"uid": "c1"}], "total": 1},
            "c1/nodes.json": {"items": [{"uid": "n1"}]},
            "nodes/n1.json": {
                "uid": "n1",
                "node_type": "raspberrypi4-64",
                "architecture": {"platform_type": "arm64"},
                "gpu": {"gpu": False},
            },
        }
        be = reference_api.ReferenceApiBackend()
        with mock.patch.object(reference_api, "get_json", _fake_get_json(mapping)):
            devs = be.list_devices()
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0].machine_type, "raspberrypi4-64")
        self.assertEqual(devs[0].architecture, "arm64")
        # reference API carries no live state
        self.assertIsNone(devs[0].free_now)
        self.assertFalse(devs[0].live_state_known)

    def test_probe_live_status_all_missing(self):
        be = reference_api.ReferenceApiBackend()
        with mock.patch.object(reference_api, "get_json", _fake_get_json({})):
            findings = be.probe_live_status()
        self.assertIsNone(findings["live_endpoint"])
        self.assertFalse(be.reports_live_state)
        self.assertTrue(all(not c["ok"] for c in findings["candidates"]))


class TestFactory(unittest.TestCase):
    def test_reference_backend(self):
        self.assertEqual(get_backend("reference_api").name, "reference_api")

    def test_unknown_backend_raises(self):
        with self.assertRaises(ValueError):
            get_backend("nonsense")

    def test_blazar_requires_credentials(self):
        # BlazarBackend talks to Keystone/Blazar over REST, so python-chi is no
        # longer a dependency. What it does require is credentials: one
        # application-credential openrc per site, via CHAMELEON_RC_GLOB.
        import os
        from advisor import config

        saved_env = os.environ.pop("CHAMELEON_RC_GLOB", None)
        saved_cfg = config.settings.chameleon_rc_glob
        object.__setattr__(config.settings, "chameleon_rc_glob", None)
        try:
            with self.assertRaises(RuntimeError):
                get_backend("blazar")
        finally:
            object.__setattr__(config.settings, "chameleon_rc_glob", saved_cfg)
            if saved_env is not None:
                os.environ["CHAMELEON_RC_GLOB"] = saved_env


if __name__ == "__main__":
    unittest.main()
