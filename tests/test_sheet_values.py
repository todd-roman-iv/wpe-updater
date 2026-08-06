import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wpe_updates_sync import (
    AccountConfig,
    SheetConfig,
    build_php_format_requests,
    build_header_values,
    build_status_only_updates,
    build_sheet_values,
    column_to_index,
    index_to_column,
    load_update_statuses,
    status_from_update_row,
)


class SheetValueTests(unittest.TestCase):
    def config(self):
        return SheetConfig(
            spreadsheet_id="sheet",
            worksheet_name="WPE Updates Q3 2026",
            first_data_row=3,
            last_data_row=5,
            accounts=[
                AccountConfig("sociusdms", "A"),
                AccountConfig("sociusdms2", "F"),
                AccountConfig("sociusdms3", "K"),
            ],
            write_headers=True,
            preserve_status=True,
        )

    def test_column_conversion(self):
        for index, column in [(1, "A"), (26, "Z"), (27, "AA"), (53, "BA")]:
            self.assertEqual(column_to_index(column), index)
            self.assertEqual(index_to_column(index), column)

    def test_builds_five_column_account_blocks(self):
        values = build_sheet_values(
            self.config(),
            {
                "sociusdms": [
                    {"site_name": "Alpha", "environment_name": "alpha", "environment_type": "", "php_version": "7.4"}
                ],
                "sociusdms2": [
                    {"site_name": "Beta", "environment_name": "betastg", "environment_type": "", "php_version": "8.2"}
                ],
                "sociusdms3": [],
            },
        )

        self.assertEqual(values[0][0:5], [1, "Alpha", "alpha", "", "7.4"])
        self.assertEqual(values[0][5:10], [1, "Beta", "betastg", "", "8.2"])
        self.assertEqual(values[0][10:15], ["", "", "", "", ""])

    def test_preserves_status_by_site_and_environment(self):
        values = build_sheet_values(
            self.config(),
            {
                "sociusdms": [
                    {"site_name": "Alpha", "environment_name": "alpha", "environment_type": "", "php_version": ""}
                ],
            },
            existing_statuses={"sociusdms": {("Alpha", "alpha"): "Complete"}},
        )

        self.assertEqual(values[0][0:5], [1, "Alpha", "alpha", "Complete", ""])

    def test_headers_match_quarterly_layout(self):
        headers = build_header_values(self.config())

        self.assertEqual(headers[0][0], "=SUM(A3:A5)")
        self.assertEqual(headers[0][1], "sociusdms")
        self.assertEqual(headers[1][0:5], ["", "Site Name", "Environment Name", "Status", "PHP"])

    def test_php_format_requests_clear_and_color_php_columns(self):
        requests = build_php_format_requests(
            self.config(),
            {
                "sociusdms": [
                    {"site_name": "Alpha", "environment_name": "alpha", "environment_type": "", "php_version": "7.4"}
                ],
                "sociusdms2": [
                    {"site_name": "Beta", "environment_name": "betastg", "environment_type": "", "php_version": "8.2"}
                ],
            },
            sheet_id=123,
        )

        self.assertEqual(requests[0]["repeatCell"]["range"]["startColumnIndex"], 4)
        self.assertEqual(requests[1]["repeatCell"]["range"]["startColumnIndex"], 4)
        self.assertEqual(requests[2]["repeatCell"]["range"]["startColumnIndex"], 9)
        self.assertEqual(requests[3]["repeatCell"]["range"]["startColumnIndex"], 9)

    def test_status_from_update_row_marks_plugin_threshold(self):
        status = status_from_update_row(
            {
                "Site": "Alpha",
                "Environment": "alpha",
                "Plugin Updates": "5",
                "WordPress Update": "",
                "Vulnerabilities": "0",
            }
        )

        self.assertEqual(status, "Plugins Outdated")

    def test_status_from_update_row_marks_critical_first(self):
        status = status_from_update_row(
            {
                "Site": "Alpha",
                "Environment": "alpha",
                "Plugin Updates": "8",
                "WordPress Update": "6.8.2",
                "Vulnerabilities": "1",
            }
        )

        self.assertEqual(status, "Critical Update Needed")

    def test_status_from_update_row_marks_vulnerable_plugin_aria_text(self):
        status = status_from_update_row(
            {
                "Site": "Candor Roofing Solutions",
                "Environment": "candorroofing1",
                "Plugin Update Label": (
                    "We have detected vulnerabilities with plugins on this site "
                    "environment. We recommend you update these plugins now to "
                    "keep your sites secure."
                ),
                "Plugin Updates": "4 outdated",
            }
        )

        self.assertEqual(status, "Critical Update Needed")

    def test_status_from_update_row_marks_wp_outdated_before_plugin_count(self):
        status = status_from_update_row(
            {
                "Site": "Alpha",
                "Environment": "alpha",
                "Plugin Updates": "5",
                "WordPress Update Available": "6.8.2",
                "Vulnerabilities": "0",
            }
        )

        self.assertEqual(status, "WP Outdated")

    def test_update_status_overrides_preserved_status(self):
        values = build_sheet_values(
            self.config(),
            {
                "sociusdms": [
                    {"site_name": "Alpha", "environment_name": "alpha", "environment_type": "", "php_version": "8.2"}
                ],
            },
            existing_statuses={"sociusdms": {("Alpha", "alpha"): "Complete"}},
            update_statuses={("alpha", "alpha"): "Critical Update Needed"},
        )

        self.assertEqual(values[0][0:5], [1, "Alpha", "alpha", "Critical Update Needed", "8.2"])

    def test_load_update_statuses_accepts_direct_status_column(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "statuses.csv"
            path.write_text(
                "account,site,environment,status\n"
                "sociusdms,Alpha,alpha,Critical Update Needed\n",
                encoding="utf-8",
            )

            statuses = load_update_statuses(path)

        self.assertEqual(statuses[("alpha", "alpha")], "Critical Update Needed")

    def test_load_update_statuses_prefers_status_override(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "statuses.csv"
            path.write_text(
                "account,site,environment,status,status_override\n"
                "sociusdms,Alpha,alpha,Plugins Outdated,Plugin Update Error\n",
                encoding="utf-8",
            )

            statuses = load_update_statuses(path)

        self.assertEqual(statuses[("alpha", "alpha")], "Plugin Update Error")

    def test_load_update_statuses_accepts_update_complete(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "statuses.csv"
            path.write_text(
                "account,site,environment,status\n"
                "sociusdms,Alpha,alpha,Update Complete\n",
                encoding="utf-8",
            )

            statuses = load_update_statuses(path)

        self.assertEqual(statuses[("alpha", "alpha")], "Update Complete")

    def test_load_update_statuses_accepts_dns_elsewhere(self):
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "statuses.csv"
            path.write_text(
                "account,site,environment,status\n"
                "sociusdms,Alpha,alpha,DNS Elsewhere\n",
                encoding="utf-8",
            )

            statuses = load_update_statuses(path)

        self.assertEqual(statuses[("alpha", "alpha")], "DNS Elsewhere")

    def test_status_only_updates_only_matching_rows_by_default(self):
        values = [
            [1, "Alpha", "alpha", "Critical Update Needed", "8.2"],
            [1, "Beta", "beta", "Plugins Outdated", "8.2"],
        ]

        updates = build_status_only_updates(
            self.config(),
            values,
            {("alpha", "alpha"): "Plugin Update Error"},
        )

        self.assertEqual(updates, [{"range": "'WPE Updates Q3 2026'!D3", "values": [["Plugin Update Error"]]}])

    def test_status_only_can_clear_missing_auto_statuses_when_requested(self):
        values = [
            [1, "Alpha", "alpha", "Critical Update Needed", "8.2"],
            [1, "Beta", "beta", "Manual Review", "8.2"],
        ]

        updates = build_status_only_updates(
            self.config(),
            values,
            {},
            clear_missing_auto_statuses=True,
        )

        self.assertEqual(updates, [{"range": "'WPE Updates Q3 2026'!D3", "values": [[""]]}])


if __name__ == "__main__":
    unittest.main()
