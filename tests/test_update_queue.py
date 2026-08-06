import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wpe_update_queue import build_queue_item, load_queue


class UpdateQueueTests(unittest.TestCase):
    def test_critical_status_queues_plugin_update_and_review(self):
        item = build_queue_item(
            {
                "account": "sociusdms2",
                "site": "Candor Roofing Solutions",
                "environment": "candorroofing1",
                "status": "Critical Update Needed",
            }
        )

        self.assertIsNotNone(item)
        self.assertTrue(item.update_plugins)
        self.assertFalse(item.update_themes)
        self.assertTrue(item.requires_review)

    def test_theme_update_column_queues_theme_update(self):
        item = build_queue_item(
            {
                "account": "sociusdms",
                "site": "Alpha",
                "environment": "alpha",
                "status": "Plugins Outdated",
                "theme_updates": "2",
            }
        )

        self.assertIsNotNone(item)
        self.assertTrue(item.update_plugins)
        self.assertTrue(item.update_themes)

    def test_load_queue_sorts_critical_first(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "statuses.csv"
            path.write_text(
                "account,site,environment,status\n"
                "sociusdms,Alpha,alpha,Plugins Outdated\n"
                "sociusdms2,Beta,beta,Critical Update Needed\n",
                encoding="utf-8",
            )

            queue = load_queue(path)

        self.assertEqual([item.environment for item in queue], ["beta", "alpha"])


if __name__ == "__main__":
    unittest.main()
