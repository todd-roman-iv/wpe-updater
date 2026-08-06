import unittest

from wpe_update_runner import RunnerItem, filter_items, validate_apply, write_completion_statuses
from pathlib import Path
from tempfile import TemporaryDirectory


class UpdateRunnerTests(unittest.TestCase):
    def items(self):
        return [
            RunnerItem("a1", "Site 1", "env1", "Plugins Outdated", True, False, False, True, ""),
            RunnerItem("a1", "Site 2", "env2", "Critical Update Needed", True, False, True, True, ""),
            RunnerItem("a2", "Site 3", "env3", "Plugins Outdated", True, False, False, False, "No backup"),
        ]

    def test_filter_excludes_critical_by_default(self):
        filtered = filter_items(self.items(), account=None, environment=None, include_critical=False)

        self.assertEqual([item.environment for item in filtered], ["env1", "env3"])

    def test_apply_blocks_failed_preflight(self):
        rows = validate_apply(self.items(), apply=True)
        blocked = [row for row in rows if row["environment"] == "env3"][0]

        self.assertEqual(blocked["result"], "blocked")
        self.assertIn("No backup", blocked["message"])

    def test_completion_status_file_only_writes_complete_rows(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "complete.csv"
            count = write_completion_statuses(
                path,
                [
                    {"account": "a1", "site": "Site", "environment": "env1", "result": "complete"},
                    {"account": "a1", "site": "Site", "environment": "env2", "result": "blocked"},
                ],
            )
            content = path.read_text(encoding="utf-8")

        self.assertEqual(count, 1)
        self.assertIn("Update Complete", content)
        self.assertIn("env1", content)
        self.assertNotIn("env2", content)


if __name__ == "__main__":
    unittest.main()
