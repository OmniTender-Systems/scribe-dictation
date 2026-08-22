"""Unit tests for the GitHub release updater module."""

import unittest
from unittest.mock import MagicMock, patch

from scribe_dictation.updater import (
    CURRENT_VERSION,
    fetch_latest_release_info,
    is_newer_version,
    parse_version,
)


class TestUpdater(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("0.2.0"), (0, 2, 0))
        self.assertEqual(parse_version("v0.2.1"), (0, 2, 1))
        self.assertEqual(parse_version("v1.0"), (1, 0, 0))
        self.assertEqual(parse_version("v2.1.3-beta"), (2, 1, 3))

    def test_is_newer_version(self):
        self.assertTrue(is_newer_version("v0.3.0", "0.2.0"))
        self.assertTrue(is_newer_version("v0.2.1", "0.2.0"))
        self.assertTrue(is_newer_version("v1.0.0", "0.2.0"))
        self.assertFalse(is_newer_version("v0.2.0", "0.2.0"))
        self.assertFalse(is_newer_version("v0.1.9", "0.2.0"))

    @patch("urllib.request.urlopen")
    def test_fetch_latest_release_info_when_newer(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"tag_name": "v9.9.9", "name": "Version 9.9.9", "html_url": "https://github.com/subtiliorars-sys/scribe-dictation/releases/tag/v9.9.9", "body": "Notes"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        info = fetch_latest_release_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["tag_name"], "v9.9.9")
        self.assertEqual(info["name"], "Version 9.9.9")

    @patch("urllib.request.urlopen")
    def test_fetch_latest_release_info_when_current(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = (
            f'{{"tag_name": "v{CURRENT_VERSION}", "name": "Current"}}'.encode("utf-8")
        )
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        info = fetch_latest_release_info()
        self.assertIsNone(info)


if __name__ == "__main__":
    unittest.main()
