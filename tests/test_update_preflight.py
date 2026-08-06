import unittest

from wpe_update_preflight import has_nextgen_pair, php_warning


class UpdatePreflightTests(unittest.TestCase):
    def test_php_warning_for_old_php(self):
        self.assertIn("older than 8.1", php_warning("7.4"))

    def test_php_warning_empty_for_modern_php(self):
        self.assertEqual(php_warning("8.2"), "")

    def test_detects_nextgen_pair_by_slug(self):
        inventory = {
            "alpha": {
                "nextgen-gallery",
                "nextgen-gallery-pro",
            }
        }

        self.assertTrue(has_nextgen_pair("alpha", inventory))

    def test_does_not_detect_single_nextgen_plugin(self):
        inventory = {"alpha": {"nextgen-gallery"}}

        self.assertFalse(has_nextgen_pair("alpha", inventory))


if __name__ == "__main__":
    unittest.main()
