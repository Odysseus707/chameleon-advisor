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


class TestKeystoneAuth(unittest.TestCase):
    """keystone_auth / public_endpoint, split out of probe_site.

    probe_site's auth and catalog handling had no coverage at all, and a
    connected session is about to depend on both: on the token body for the
    project name, and on the catalog for the Zun endpoint as well as Blazar's.
    """

    def setUp(self):
        from advisor.availability import blazar
        self.blazar = blazar
        self.app_cred_env = {
            "OS_AUTH_URL": "https://chi.edge.example.org:5000/v3",
            "OS_APPLICATION_CREDENTIAL_ID": "cred-id",
            "OS_APPLICATION_CREDENTIAL_SECRET": "cred-secret",
        }

    def _token_body(self):
        return {"token": {
            "project": {"id": "p-123", "name": "CHI-000000"},
            "catalog": [
                {"type": "reservation", "endpoints": [
                    {"interface": "internal", "url": "https://internal.invalid/"},
                    {"interface": "public", "url": "https://blazar.example.org/v1/"},
                ]},
                {"type": "container", "endpoints": [
                    {"interface": "public", "url": "https://zun.example.org/"},
                ]},
                {"type": "identity", "endpoints": [
                    {"interface": "public", "url": "https://keystone.example.org/"},
                ]},
            ],
        }}

    def test_no_credentials_is_an_error_not_a_crash(self):
        token, body, err = self.blazar.keystone_auth({"OS_AUTH_URL": "https://x/v3"})
        self.assertIsNone(token)
        self.assertIsNone(body)
        self.assertEqual(err, "no credentials or OS_AUTH_URL in this RC")

    def test_missing_auth_url_is_an_error(self):
        env = dict(self.app_cred_env)
        del env["OS_AUTH_URL"]
        _, _, err = self.blazar.keystone_auth(env)
        self.assertEqual(err, "no credentials or OS_AUTH_URL in this RC")

    def test_401_is_reported_not_raised(self):
        resp = mock.Mock(status_code=401, headers={})
        with mock.patch.object(self.blazar.requests, "post", return_value=resp):
            token, body, err = self.blazar.keystone_auth(self.app_cred_env)
        self.assertIsNone(token)
        self.assertEqual(err, "keystone HTTP 401")

    def test_network_failure_is_reported_not_raised(self):
        import requests as _rq
        with mock.patch.object(self.blazar.requests, "post",
                               side_effect=_rq.ConnectTimeout("boom")):
            token, _, err = self.blazar.keystone_auth(self.app_cred_env)
        self.assertIsNone(token)
        self.assertIn("ConnectTimeout", err)

    def test_success_returns_token_and_body(self):
        resp = mock.Mock(status_code=201, headers={"X-Subject-Token": "tok-abc"})
        resp.json.return_value = self._token_body()
        with mock.patch.object(self.blazar.requests, "post", return_value=resp) as post:
            token, body, err = self.blazar.keystone_auth(self.app_cred_env)
        self.assertIsNone(err)
        self.assertEqual(token, "tok-abc")
        # the project rides along on the same response - no second round trip
        self.assertEqual(body["token"]["project"]["name"], "CHI-000000")
        # app-credential auth, not password
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["auth"]["identity"]["methods"], ["application_credential"])

    def test_auth_url_without_v3_suffix_is_normalized(self):
        env = dict(self.app_cred_env, OS_AUTH_URL="https://chi.edge.example.org:5000")
        resp = mock.Mock(status_code=200, headers={"X-Subject-Token": "t"})
        resp.json.return_value = self._token_body()
        with mock.patch.object(self.blazar.requests, "post", return_value=resp) as post:
            self.blazar.keystone_auth(env)
        self.assertTrue(post.call_args.args[0].endswith("/v3/auth/tokens"))

    def test_public_endpoint_picks_public_and_strips_trailing_slash(self):
        body = self._token_body()
        self.assertEqual(self.blazar.public_endpoint(body, "reservation"),
                         "https://blazar.example.org/v1")

    def test_public_endpoint_finds_zun(self):
        """Phase C needs the container endpoint out of the same catalog."""
        self.assertEqual(self.blazar.public_endpoint(self._token_body(), "container"),
                         "https://zun.example.org")

    def test_public_endpoint_missing_type_is_none(self):
        self.assertIsNone(self.blazar.public_endpoint(self._token_body(), "volume"))
        self.assertIsNone(self.blazar.public_endpoint(None, "reservation"))

    def test_probe_site_surfaces_auth_error_unchanged(self):
        """probe_site's contract must survive the extraction."""
        out = self.blazar.probe_site({"OS_AUTH_URL": "https://x/v3"}, "some-rc.sh")
        self.assertEqual(out["error"], "no credentials or OS_AUTH_URL in this RC")
        self.assertEqual(set(out), {"site", "blazar", "kind", "nodes", "error"})
        self.assertEqual(out["site"], "some-rc.sh")

    def test_probe_site_reports_missing_reservation_endpoint(self):
        resp = mock.Mock(status_code=200, headers={"X-Subject-Token": "t"})
        resp.json.return_value = {"token": {"catalog": []}}
        with mock.patch.object(self.blazar.requests, "post", return_value=resp):
            out = self.blazar.probe_site(self.app_cred_env)
        self.assertEqual(out["error"], "no reservation endpoint in catalog")


if __name__ == "__main__":
    unittest.main()
