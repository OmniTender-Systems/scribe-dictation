import unittest
from unittest.mock import patch, MagicMock
from scribe_dictation.licensing import (
    get_machine_fingerprint,
    generate_signature,
    is_offline_cache_valid,
    verify_license_online,
    verify_license_key,
    generate_license_key,
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

    def test_generate_and_verify_license_key(self):
        key = generate_license_key()
        self.assertTrue(verify_license_key(key))

    def test_verify_license_key_rejects_tampering(self):
        key = generate_license_key()
        tampered = key[:-1] + ("0" if key[-1] != "0" else "1")
        self.assertFalse(verify_license_key(tampered))

    def test_verify_license_key_rejects_garbage(self):
        self.assertFalse(verify_license_key("not-a-real-key"))
        self.assertFalse(verify_license_key(""))

    def test_verify_license_online_success_caches(self):
        key = generate_license_key()
        self.assertTrue(verify_license_online(key))
        self.assertTrue(is_offline_cache_valid())

    def test_verify_license_online_rejects_invalid(self):
        self.assertFalse(verify_license_online("SCRIBE-0000-0000-0000-00000000"))
