import unittest
from unittest.mock import patch, MagicMock
from scribe_dictation.licensing import (
    get_machine_fingerprint,
    generate_signature,
    is_offline_cache_valid,
    verify_license_online,
    cache_activation,
    deactivate_license,
)


class TestLicensing(unittest.TestCase):
    def setUp(self):
        # We need to isolate settings for testing
        self.settings_patcher = patch("scribe_dictation.licensing.QSettings")
        self.mock_qsettings_class = self.settings_patcher.start()
        self.mock_settings = MagicMock()
        self.mock_qsettings_class.return_value = self.mock_settings

        # Store settings dictionary in mock
        self.settings_db = {}
        self.mock_settings.value.side_effect = (
            lambda key, default=None: self.settings_db.get(key, default)
        )
        self.mock_settings.setValue.side_effect = (
            lambda key, value: self.settings_db.update({key: value})
        )
        self.mock_settings.remove.side_effect = lambda key: self.settings_db.pop(
            key, None
        )

    def tearDown(self):
        self.settings_patcher.stop()

    def test_get_machine_fingerprint(self):
        fingerprint = get_machine_fingerprint()
        self.assertIsNotNone(fingerprint)
        self.assertGreater(len(fingerprint), 10)

    def test_signature_generation(self):
        key = "test-key-123"
        fingerprint = "fake-fingerprint"
        sig1 = generate_signature(key, fingerprint)
        sig2 = generate_signature(key, fingerprint)
        self.assertEqual(sig1, sig2)

        # Change fingerprint, should yield different signature
        self.assertNotEqual(sig1, generate_signature(key, "different-fingerprint"))

    def test_offline_cache_invalid_by_default(self):
        self.assertFalse(is_offline_cache_valid())

    def test_cache_and_verify_offline(self):
        key = "valid-key-999"
        cache_activation(key)
        self.assertTrue(is_offline_cache_valid())

        # Deactivate
        deactivate_license()
        self.assertFalse(is_offline_cache_valid())

    @patch("requests.post")
    def test_verify_lemonsqueezy_online_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "activated": True,
            "license_key": {"status": "active"},
        }
        mock_post.return_value = mock_response

        with patch("scribe_dictation.licensing.LICENSE_PROVIDER", "lemonsqueezy"):
            success = verify_license_online("test-key")
            self.assertTrue(success)
            self.assertTrue(is_offline_cache_valid())

    @patch("requests.post")
    def test_verify_lemonsqueezy_online_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "activated": False,
            "license_key": {"status": "expired"},
        }
        mock_post.return_value = mock_response

        with patch("scribe_dictation.licensing.LICENSE_PROVIDER", "lemonsqueezy"):
            success = verify_license_online("bad-key")
            self.assertFalse(success)

    @patch("requests.post")
    def test_verify_gumroad_online_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "purchase": {"refunded": False, "chargebacked": False},
        }
        mock_post.return_value = mock_response

        with patch("scribe_dictation.licensing.LICENSE_PROVIDER", "gumroad"):
            success = verify_license_online("test-key")
            self.assertTrue(success)
            self.assertTrue(is_offline_cache_valid())
